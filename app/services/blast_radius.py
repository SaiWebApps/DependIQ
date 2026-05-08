"""
Blast radius computation and explanation service.

Given a package update, determines which projects are affected and in what order,
then uses LLM to explain WHY each project is affected and what might break.
"""

import logging
import time
import uuid
from pathlib import Path
from typing import Any

from app.graph import BlastRadiusResult, GraphService
from app.services import stream_publisher
from app.services.llm.agent import Agent
from app.services.llm.events import AnalysisEvent
from app.services.llm.router import TaskType

logger = logging.getLogger(__name__)

# In-memory store for blast radius results, keyed by blast_radius_id.
# Each entry includes a "stored_at" timestamp for TTL cleanup.
_blast_results: dict[str, dict[str, Any]] = {}

# TTL for stored results: 1 hour
_RESULT_TTL_SECONDS = 3600

# Path to the chain reaction prompt template
_PROMPT_TEMPLATE_PATH = (
    Path(__file__).parent / "llm" / "prompts" / "trace_chain_reaction.md"
)


def store_blast_result(br_id: str, result: dict[str, Any]) -> None:
    """Store a blast radius result with a timestamp for TTL expiry."""
    _blast_results[br_id] = {**result, "stored_at": time.time()}
    _cleanup_expired()


def get_blast_result(br_id: str) -> dict[str, Any] | None:
    """Retrieve a blast radius result if it exists and hasn't expired."""
    entry = _blast_results.get(br_id)
    if entry is None:
        return None
    if time.time() - entry["stored_at"] > _RESULT_TTL_SECONDS:
        del _blast_results[br_id]
        return None
    return entry


def _cleanup_expired() -> None:
    """Remove entries older than the TTL. Called on each store to keep memory bounded."""
    now = time.time()
    expired = [
        k
        for k, v in _blast_results.items()
        if now - v["stored_at"] > _RESULT_TTL_SECONDS
    ]
    for k in expired:
        del _blast_results[k]


def _load_prompt_template() -> str:
    """Load the chain reaction prompt template from disk."""
    return _PROMPT_TEMPLATE_PATH.read_text()


def _render_prompt(
    template: str,
    package_name: str,
    ecosystem: str,
    from_version: str,
    to_version: str,
    project_name: str,
    distance: int,
    impact_type: str,
    dependency_path: str,
) -> str:
    """Render the prompt template with concrete values."""
    return (
        template.replace("{{ package_name }}", package_name)
        .replace("{{ ecosystem }}", ecosystem)
        .replace("{{ from_version }}", from_version or "unknown")
        .replace("{{ to_version }}", to_version or "latest")
        .replace("{{ project_name }}", project_name)
        .replace("{{ distance }}", str(distance))
        .replace("{{ impact_type }}", impact_type)
        .replace("{{ dependency_path }}", dependency_path)
    )


def _severity_for_distance(distance: int) -> str:
    """Determine severity based on hop distance from the updated package."""
    if distance <= 1:
        return "high"
    elif distance == 2:
        return "medium"
    else:
        return "low"


class BlastRadiusService:
    """Orchestrates blast radius computation and streaming explanation."""

    def __init__(
        self,
        graph_service: GraphService | None = None,
        agent: Agent | None = None,
    ):
        self.graph_service = graph_service or GraphService()
        self.agent = agent or Agent()

    async def compute_blast_radius(
        self,
        workspace_id: str,
        package_name: str,
        ecosystem: str,
        from_version: str | None = None,
        to_version: str | None = None,
    ) -> dict[str, Any]:
        """
        Query the graph for affected projects, return structured result.

        The result is stored in memory for the streaming explanation to reference.
        Returns immediately with a stream_url the client can connect to for explanation.
        """
        # Query the dependency graph
        graph_result: BlastRadiusResult = await self.graph_service.query_blast_radius(
            workspace_id=workspace_id,
            package_name=package_name,
            ecosystem=ecosystem,
        )

        # Sort affected projects by distance (direct first)
        affected_sorted = sorted(
            graph_result.affected_projects, key=lambda p: p.get("distance", 999)
        )

        # Generate a unique ID for this blast radius computation
        br_id = f"br-{uuid.uuid4().hex[:12]}"

        result = {
            "id": br_id,
            "package": package_name,
            "ecosystem": ecosystem,
            "from_version": from_version,
            "to_version": to_version,
            "affected_projects": affected_sorted,
            "total_affected": len(affected_sorted),
            "computed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        # Store for the explain stream to use later
        store_blast_result(br_id, result)

        return result

    async def explain_chain_reaction(self, blast_radius_id: str, task_id: str) -> None:
        """
        Stream LLM explanation of the chain reaction.

        For each affected project (in order of distance):
        1. Explain HOW it's affected (direct dep? transitive? API consumer?)
        2. Explain WHAT might break (breaking changes in the version diff)
        3. Suggest the fix order

        Publishes AnalysisEvents via stream_publisher as it reasons through each hop.
        """
        # Create the stream so subscribers can connect
        stream_publisher.create_stream(task_id)

        result = get_blast_result(blast_radius_id)
        if result is None:
            await stream_publisher.publish_event(
                task_id,
                AnalysisEvent.error(
                    f"Blast radius {blast_radius_id} not found or expired"
                ),
            )
            await stream_publisher.complete_stream(task_id)
            return

        affected_projects = result["affected_projects"]
        total = len(affected_projects)

        if total == 0:
            await stream_publisher.publish_event(
                task_id,
                AnalysisEvent.result("No projects affected by this update.", data={}),
            )
            await stream_publisher.complete_stream(task_id)
            return

        # Load prompt template once
        template = _load_prompt_template()

        package_name = result["package"]
        ecosystem = result["ecosystem"]
        from_version = result.get("from_version") or "unknown"
        to_version = result.get("to_version") or "latest"

        for idx, project in enumerate(affected_projects):
            project_name = project.get("name", "unknown")
            distance = project.get("distance", 1)
            impact_type = project.get("impact_type", "direct")
            pct = int(((idx + 1) / total) * 100)

            # Publish progress
            phase = f"Analyzing {project_name} ({idx + 1}/{total})"
            await stream_publisher.publish_event(
                task_id, AnalysisEvent.progress(phase, pct)
            )

            # Build the prompt for this specific project hop
            dependency_path = (
                f"{package_name} -> {project_name}"
                if distance == 1
                else (
                    f"{package_name} -> ... ({distance - 1} intermediate) -> {project_name}"
                )
            )
            prompt = _render_prompt(
                template=template,
                package_name=package_name,
                ecosystem=ecosystem,
                from_version=from_version,
                to_version=to_version,
                project_name=project_name,
                distance=distance,
                impact_type=impact_type,
                dependency_path=dependency_path,
            )

            # Publish thinking event before LLM call
            await stream_publisher.publish_event(
                task_id,
                AnalysisEvent.thinking(
                    f"Analyzing how {project_name} is affected by "
                    f"{package_name} {from_version} -> {to_version} "
                    f"({impact_type} dependency, {distance} hop(s) away)"
                ),
            )

            # Call LLM for explanation
            try:
                agent_result = await self.agent.run(
                    task=TaskType.SECURITY_ANALYSIS,
                    prompt=prompt,
                    system="You are a dependency impact analyst. Be concise and specific.",
                )
                explanation = agent_result.content
            except Exception as e:
                logger.error("LLM call failed for project %s: %s", project_name, e)
                explanation = f"Unable to analyze: {e}"

            # Publish result with severity assessment
            severity = _severity_for_distance(distance)
            await stream_publisher.publish_event(
                task_id,
                AnalysisEvent.result(
                    content=explanation,
                    data={
                        "project": project_name,
                        "project_id": project.get("project_id", ""),
                        "severity": severity,
                        "distance": distance,
                        "impact_type": impact_type,
                    },
                ),
            )

        # All projects analyzed — signal completion
        await stream_publisher.complete_stream(task_id)
