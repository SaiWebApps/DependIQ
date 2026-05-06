"""
DependIQ-specific agent tasks.

Wraps the generic Agent with DependIQ business logic:
prompts, result parsing, and domain-specific tools.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field

from ..models.dependency import Dependency
from .llm import Agent, TaskType

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are DependIQ, a dependency intelligence agent. "
    "You have tools to look up real package versions from registries. "
    "Always use your tools to check actual versions — never guess from memory. "
    "Return structured JSON when asked."
)


@dataclass
class DependencyAgent:
    """High-level agent for DependIQ dependency analysis tasks."""

    agent: Agent = field(default_factory=Agent)

    async def research_latest_versions(
        self,
        dependencies: list[Dependency],
        project_type: str,
    ) -> list[Dependency]:
        """
        Research latest versions for all dependencies using live registry lookups.

        Replaces the old research_latest_versions_with_gpt which hallucinated
        versions from training data. This version uses tool_use to actually
        fetch from PyPI, npm, Maven Central, etc.
        """
        if not dependencies:
            return dependencies

        ecosystem = self._project_type_to_ecosystem(project_type)

        dep_descriptions = "\n".join(
            f"- {dep.name}: currently at {dep.current_version} ({dep.description})"
            for dep in dependencies
        )

        prompt = f"""Research the latest stable versions for these {project_type} dependencies.

Dependencies:
{dep_descriptions}

Instructions:
1. Use the fetch_package_versions tool to check the actual registries.
   - Ecosystem to use: "{ecosystem}"
   - For Maven/Gradle/SBT dependencies with a group ID (e.g., org.apache.spark:spark-core),
     pass both "group" and "artifact" fields.
2. From the registry responses, extract the latest stable version for each package.
3. Return ONLY a JSON object mapping package name to latest version:

{{"package-name": "latest-version", ...}}

Do not include any explanation, just the JSON object."""

        result = await self.agent.run(
            task=TaskType.VERSION_RESEARCH,
            prompt=prompt,
            system=SYSTEM_PROMPT,
        )

        versions = self._parse_version_response(result.content)

        for dep in dependencies:
            if dep.name in versions:
                dep.latest_version = versions[dep.name]
            else:
                # Try fuzzy match (artifact-only for Maven deps)
                artifact = dep.name.split(":")[-1] if ":" in dep.name else dep.name
                if artifact in versions:
                    dep.latest_version = versions[artifact]
                else:
                    dep.latest_version = dep.current_version

        logger.info(
            f"Version research complete: {len(versions)} versions found "
            f"using model {result.model_used} with {result.tool_calls_made} tool calls"
        )
        return dependencies

    async def extract_dependencies(
        self,
        project_type: str,
        file_content: str,
        file_name: str,
    ) -> list[Dependency]:
        """Extract dependencies from a build file using LLM analysis."""
        prompt = f"""Analyze this {project_type} build file ({file_name}) and extract ALL dependencies.

Include:
- Direct dependencies (libraries explicitly listed)
- Build tool versions (sbt, gradle, maven)
- Plugin dependencies
- Language/runtime versions (Scala, Java, Python version)

File content:
```
{file_content}
```

Return ONLY a JSON array:
[
  {{"name": "dependency-name", "current_version": "1.2.3", "description": "Brief description"}},
  ...
]"""

        result = await self.agent.run(
            task=TaskType.DEPENDENCY_EXTRACT,
            prompt=prompt,
            system=SYSTEM_PROMPT,
        )

        return self._parse_dependency_response(result.content)

    async def analyze_security(
        self,
        dependencies: list[Dependency],
        project_type: str,
    ) -> dict:
        """Analyze dependencies for known security vulnerabilities."""
        dep_list = "\n".join(
            f"- {dep.name}@{dep.current_version}" for dep in dependencies
        )

        prompt = f"""Analyze these {project_type} dependencies for security vulnerabilities.

Dependencies:
{dep_list}

Use web_fetch to check:
- https://osv.dev/v1/query for known vulnerabilities
- Any relevant security advisories

For each dependency with known issues, report:
- CVE ID (if available)
- Severity (critical/high/medium/low)
- Fixed version (if known)
- Brief description

Return JSON:
{{
  "vulnerable": [
    {{"name": "pkg", "cve": "CVE-...", "severity": "high", "fixed_in": "1.2.3", "description": "..."}}
  ],
  "clean": ["pkg1", "pkg2"],
  "unknown": ["pkg3"]
}}"""

        result = await self.agent.run(
            task=TaskType.SECURITY_ANALYSIS,
            prompt=prompt,
            system=SYSTEM_PROMPT,
        )

        try:
            return json.loads(self._extract_json(result.content))
        except (json.JSONDecodeError, ValueError):
            return {"vulnerable": [], "clean": [], "unknown": [d.name for d in dependencies]}

    def _project_type_to_ecosystem(self, project_type: str) -> str:
        mapping = {
            "python": "pypi",
            "maven": "maven",
            "gradle": "maven",
            "sbt": "maven",
            "npm": "npm",
            "node": "npm",
            "rust": "crates",
            "cargo": "crates",
            "ruby": "rubygems",
            "go": "go",
            "dart": "pub",
            "flutter": "pub",
            "elixir": "hex",
            "php": "packagist",
            "dotnet": "nuget",
            "csharp": "nuget",
        }
        return mapping.get(project_type.lower(), "pypi")

    def _parse_version_response(self, content: str) -> dict[str, str]:
        """Parse version JSON from agent response."""
        try:
            json_str = self._extract_json(content)
            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                return {k: str(v) for k, v in parsed.items()}
        except (json.JSONDecodeError, ValueError):
            logger.warning(f"Failed to parse version response: {content[:200]}")
        return {}

    def _parse_dependency_response(self, content: str) -> list[Dependency]:
        """Parse dependency JSON from agent response."""
        try:
            json_str = self._extract_json(content)
            parsed = json.loads(json_str)
            if isinstance(parsed, list):
                return [
                    Dependency(
                        name=item["name"],
                        current_version=item.get("current_version", "unknown"),
                        description=item.get("description", ""),
                    )
                    for item in parsed
                    if isinstance(item, dict) and "name" in item
                ]
        except (json.JSONDecodeError, ValueError):
            logger.warning(f"Failed to parse dependency response: {content[:200]}")
        return []

    def _extract_json(self, content: str) -> str:
        """Extract JSON from a response that might have surrounding text."""
        content = content.strip()
        # Try direct parse first
        if content.startswith(("{", "[")):
            return content

        # Strip markdown code fences
        if "```json" in content:
            content = content.split("```json", 1)[1]
            content = content.split("```", 1)[0]
            return content.strip()
        if "```" in content:
            content = content.split("```", 1)[1]
            content = content.split("```", 1)[0]
            return content.strip()

        # Find first { or [
        for i, char in enumerate(content):
            if char in ("{", "["):
                return content[i:]

        return content


# --- Sync wrappers for callers still using synchronous code ---


_default_agent: DependencyAgent | None = None


def get_dependency_agent() -> DependencyAgent:
    """Get or create the singleton DependencyAgent."""
    global _default_agent
    if _default_agent is None:
        _default_agent = DependencyAgent()
    return _default_agent


def research_latest_versions(
    dependencies: list[Dependency], project_type: str
) -> list[Dependency]:
    """
    Sync wrapper for DependencyAgent.research_latest_versions.

    Drop-in replacement for the old research_latest_versions_with_gpt.
    Can be called from synchronous background threads.
    """
    agent = get_dependency_agent()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # We're inside an async context (e.g., FastAPI) — run in a new thread's event loop
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                asyncio.run,
                agent.research_latest_versions(dependencies, project_type),
            )
            return future.result(timeout=120)
    else:
        # We're in a plain sync context (background thread, CLI, tests)
        return asyncio.run(
            agent.research_latest_versions(dependencies, project_type)
        )

