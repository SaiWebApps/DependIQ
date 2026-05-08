"""
Cross-project relationship detection service.

Analyzes multiple projects owned by a user to find:
- Shared dependencies (both depend on same package)
- Import relationships (A imports from B's published package)
- API calls (A calls B's endpoints)
- Shared databases (A and B use same DB/tables)

Uses the LLM with map_architecture prompt to infer relationships
that static analysis alone cannot detect.
"""

import asyncio
import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime
from itertools import combinations
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..graph.service import GraphRelationship, GraphService
from ..models.job import Job, JobStatus
from ..models.project_library import ProjectLibrary
from ..services.llm.agent import Agent, AgentResult
from ..services.llm.router import TaskType

logger = logging.getLogger(__name__)

# Concurrency limit for parallel LLM calls
_LLM_SEMAPHORE_LIMIT = 3

# Path to the prompt template
_PROMPT_TEMPLATE_PATH = (
    Path(__file__).parent / "llm" / "prompts" / "map_architecture.md"
)


def _load_prompt_template() -> str:
    """Load the map_architecture prompt template from disk."""
    return _PROMPT_TEMPLATE_PATH.read_text()


def _build_dependency_list(project: ProjectLibrary) -> list[str]:
    """Extract dependency names from a project's dependency_files JSON."""
    deps: list[str] = []
    if not project.dependency_files:
        return deps

    # dependency_files is a JSON dict; keys are filenames, values are content/parsed deps
    for _filename, content in project.dependency_files.items():
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and "name" in item:
                    deps.append(item["name"])
                elif isinstance(item, str):
                    deps.append(item)
        elif isinstance(content, dict):
            # e.g. {"flask": "2.0", "requests": "2.28"}
            deps.extend(content.keys())

    return deps


def _render_prompt(
    template: str,
    project_a: ProjectLibrary,
    project_b: ProjectLibrary,
    deps_a: list[str],
    deps_b: list[str],
) -> str:
    """Render the map_architecture prompt with project details."""
    files_a = ""
    files_b = ""

    # Build file tree summaries from extra_metadata if available
    if project_a.extra_metadata and "file_tree" in project_a.extra_metadata:
        files_a = "\n".join(project_a.extra_metadata["file_tree"][:50])
    if project_b.extra_metadata and "file_tree" in project_b.extra_metadata:
        files_b = "\n".join(project_b.extra_metadata["file_tree"][:50])

    rendered = template.replace("{{ project_a_name }}", project_a.project_name)
    rendered = rendered.replace(
        "{{ project_a_type }}", project_a.project_type or "unknown"
    )
    rendered = rendered.replace(
        "{{ project_a_dependencies }}",
        "\n".join(f"- {d}" for d in deps_a) or "None detected",
    )
    rendered = rendered.replace("{{ project_a_files }}", files_a or "Not available")
    rendered = rendered.replace("{{ project_b_name }}", project_b.project_name)
    rendered = rendered.replace(
        "{{ project_b_type }}", project_b.project_type or "unknown"
    )
    rendered = rendered.replace(
        "{{ project_b_dependencies }}",
        "\n".join(f"- {d}" for d in deps_b) or "None detected",
    )
    rendered = rendered.replace("{{ project_b_files }}", files_b or "Not available")

    return rendered


def _parse_llm_relationships(
    response_text: str,
    project_a_id: str,
    project_b_id: str,
) -> list[dict]:
    """Parse the LLM JSON response into relationship dicts."""
    # Strip markdown fences if present
    text = response_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last fence lines
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        logger.warning(
            "Failed to parse LLM relationship response as JSON: %s", text[:200]
        )
        return []

    if not isinstance(parsed, list):
        logger.warning("LLM response was not a JSON array")
        return []

    relationships = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        rel_type = item.get("type", "")
        if rel_type not in ("imports_from", "calls_api", "shares_db", "shares_package"):
            continue

        # Map source/target back to actual project IDs
        confidence = float(item.get("confidence", 0.6))
        evidence = item.get("evidence", "")

        relationships.append(
            {
                "source_project_id": project_a_id,
                "target_project_id": project_b_id,
                "relationship_type": rel_type,
                "confidence": min(max(confidence, 0.0), 1.0),
                "evidence": evidence,
            }
        )

    return relationships


class RelationshipService:
    """Orchestrates cross-project relationship detection."""

    def __init__(
        self,
        db: AsyncSession,
        graph_service: GraphService | None = None,
        agent: Agent | None = None,
    ) -> None:
        self.db = db
        self.graph = graph_service or GraphService()
        self.agent = agent or Agent()
        self._progress_callbacks: list = []

    def on_progress(self, callback) -> None:
        """Register a callback for progress events: callback(event_type, data)."""
        self._progress_callbacks.append(callback)

    async def _emit(self, event_type: str, data: dict) -> None:
        """Emit a progress event to all registered callbacks."""
        for cb in self._progress_callbacks:
            if asyncio.iscoroutinefunction(cb):
                await cb(event_type, data)
            else:
                cb(event_type, data)

    async def detect_relationships(
        self, user_id: str, job_id: str | None = None
    ) -> list[dict]:
        """
        Main entry point. Analyzes all projects for a user to find relationships.

        Steps:
        1. Load all projects for the user with their dependencies
        2. Find shared dependencies (pure data, no LLM needed)
        3. For each project pair, use LLM to detect deeper relationships
        4. Write discovered relationships to graph service
        5. Publish events as relationships are found
        6. Return list of all relationships discovered
        """
        # Update job status if tracking
        if job_id:
            await self._update_job_status(
                job_id, JobStatus.RUNNING, 0, "Loading projects"
            )

        # Step 1: Load all user projects
        user_uuid = uuid.UUID(user_id)
        result = await self.db.execute(
            select(ProjectLibrary)
            .where(ProjectLibrary.user_id == user_uuid)
            .order_by(ProjectLibrary.created_at)
        )
        projects = list(result.scalars().all())

        if len(projects) < 2:
            await self._emit(
                "progress",
                {"message": "Need at least 2 projects to detect relationships"},
            )
            if job_id:
                await self._update_job_status(
                    job_id, JobStatus.COMPLETED, 100, "Not enough projects"
                )
            return []

        await self._emit(
            "progress",
            {"message": f"Analyzing {len(projects)} projects for relationships"},
        )

        # Step 2: Find shared dependencies (instant, no LLM)
        all_relationships: list[dict] = []
        shared_deps = self._find_shared_dependencies(projects)
        all_relationships.extend(shared_deps)

        for rel in shared_deps:
            await self.graph.write_relationship(
                GraphRelationship(
                    source_project_id=rel["source_project_id"],
                    target_project_id=rel["target_project_id"],
                    relationship_type=rel["relationship_type"],
                    confidence=rel["confidence"],
                    metadata={
                        "package": rel.get("package", ""),
                        "evidence": rel.get("evidence", ""),
                    },
                )
            )
            await self._emit("result", rel)

        if job_id:
            await self._update_job_status(
                job_id,
                JobStatus.RUNNING,
                30,
                f"Found {len(shared_deps)} shared dependencies",
            )

        # Step 3: LLM analysis for deeper relationships
        pairs = list(combinations(range(len(projects)), 2))
        total_pairs = len(pairs)
        semaphore = asyncio.Semaphore(_LLM_SEMAPHORE_LIMIT)

        async def analyze_pair(idx: int, i: int, j: int) -> list[dict]:
            async with semaphore:
                await self._emit(
                    "progress",
                    {
                        "message": f"Analyzing pair {idx + 1}/{total_pairs}: "
                        f"{projects[i].project_name} <-> {projects[j].project_name}"
                    },
                )
                return await self._detect_with_llm(projects[i], projects[j])

        tasks = [analyze_pair(idx, i, j) for idx, (i, j) in enumerate(pairs)]

        pair_results = await asyncio.gather(*tasks, return_exceptions=True)

        for idx, result in enumerate(pair_results):
            if isinstance(result, Exception):
                logger.error("LLM analysis failed for pair %d: %s", idx, result)
                continue

            for rel in result:
                all_relationships.append(rel)
                await self.graph.write_relationship(
                    GraphRelationship(
                        source_project_id=rel["source_project_id"],
                        target_project_id=rel["target_project_id"],
                        relationship_type=rel["relationship_type"],
                        confidence=rel["confidence"],
                        metadata={"evidence": rel.get("evidence", "")},
                    )
                )
                await self._emit("result", rel)

            # Update progress proportionally
            if job_id:
                pair_progress = 30 + int((idx + 1) / total_pairs * 70)
                await self._update_job_status(
                    job_id,
                    JobStatus.RUNNING,
                    pair_progress,
                    f"Analyzed {idx + 1}/{total_pairs} pairs",
                )

        # Step 4: Mark complete
        if job_id:
            await self._update_job_status(
                job_id,
                JobStatus.COMPLETED,
                100,
                f"Found {len(all_relationships)} relationships",
            )

        await self._emit(
            "progress",
            {"message": f"Complete: {len(all_relationships)} relationships detected"},
        )

        return all_relationships

    def _find_shared_dependencies(self, projects: list[ProjectLibrary]) -> list[dict]:
        """
        Pure data analysis: find packages used by multiple projects.

        No LLM needed — just set intersection on dependency lists.
        These relationships have confidence=1.0 (certain).
        """
        # Build package -> [project_ids] mapping
        package_to_projects: dict[str, list[tuple[str, str]]] = defaultdict(list)

        for project in projects:
            deps = _build_dependency_list(project)
            for dep_name in deps:
                normalized = dep_name.lower().strip()
                if normalized:
                    package_to_projects[normalized].append(
                        (str(project.id), project.project_name)
                    )

        # Find packages used by 2+ projects
        relationships: list[dict] = []
        for package, project_list in package_to_projects.items():
            if len(project_list) < 2:
                continue

            # Create a relationship for each unique pair sharing this package
            for (id_a, name_a), (id_b, name_b) in combinations(project_list, 2):
                relationships.append(
                    {
                        "source_project_id": id_a,
                        "source_name": name_a,
                        "target_project_id": id_b,
                        "target_name": name_b,
                        "relationship_type": "shares_package",
                        "confidence": 1.0,
                        "package": package,
                        "evidence": f"Both projects depend on '{package}'",
                    }
                )

        return relationships

    async def _detect_with_llm(
        self, project_a: ProjectLibrary, project_b: ProjectLibrary
    ) -> list[dict]:
        """
        Use LLM to analyze two projects and infer deeper relationships.

        Feeds project summaries, dependencies, and file trees to the LLM
        and parses structured JSON response.
        """
        deps_a = _build_dependency_list(project_a)
        deps_b = _build_dependency_list(project_b)

        # Skip LLM if neither project has meaningful data to analyze
        if not deps_a and not deps_b:
            return []

        template = _load_prompt_template()
        prompt = _render_prompt(template, project_a, project_b, deps_a, deps_b)

        try:
            result: AgentResult = await self.agent.run(
                task=TaskType.SECURITY_ANALYSIS,  # Uses sonnet-level model for analysis
                prompt=prompt,
                system="You are a software architecture analyst. Analyze project relationships and respond with JSON only.",
            )
        except Exception as e:
            logger.error(
                "LLM call failed for pair %s <-> %s: %s",
                project_a.project_name,
                project_b.project_name,
                e,
            )
            return []

        # Parse the LLM response
        relationships = _parse_llm_relationships(
            result.content,
            str(project_a.id),
            str(project_b.id),
        )

        # Enrich with project names
        for rel in relationships:
            rel["source_name"] = project_a.project_name
            rel["target_name"] = project_b.project_name

        return relationships

    async def _update_job_status(
        self, job_id: str, status: JobStatus, progress: int, step: str
    ) -> None:
        """Update the tracking job's status in the database."""
        job_uuid = uuid.UUID(job_id)
        values = {
            "status": status.value,
            "progress_percentage": progress,
            "current_step": step,
            "updated_at": datetime.utcnow(),
        }
        if status == JobStatus.RUNNING and progress == 0:
            values["started_at"] = datetime.utcnow()
        if status == JobStatus.COMPLETED:
            values["completed_at"] = datetime.utcnow()

        await self.db.execute(update(Job).where(Job.id == job_uuid).values(**values))
        await self.db.commit()
