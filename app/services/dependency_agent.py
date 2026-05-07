"""
DependIQ-specific agent tasks.

Wraps the generic Agent with DependIQ business logic:
prompts, result parsing, and domain-specific tools.
"""

import asyncio
import concurrent.futures
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from ..models.dependency import Dependency
from ..models.exclusions import ArtifactExclusionConfig
from .llm import Agent, TaskType

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are DependIQ, a dependency intelligence agent. "
    "You have tools to look up real package versions from registries. "
    "Always use your tools to check actual versions — never guess from memory. "
    "Return structured JSON when asked."
)

_MAX_STRUCTURE_SUMMARY = 50
_MAX_DIRECTORIES = 30
_MAX_PRIORITY_FILES = 15
_ANALYZABLE_EXTENSIONS = frozenset({
    ".scala", ".java", ".py", ".sbt", ".gradle", ".kts",
    ".xml", ".conf", ".properties", ".yml", ".yaml",
})
_EXCLUDED_PATH_SEGMENTS = frozenset({
    "target/", "build/", ".gradle/", "__pycache__/", ".git/",
    "node_modules/", ".idea/", ".vscode/", ".settings/",
})

# Maximum length for dependency name/version strings in prompts
_MAX_DEP_FIELD_LENGTH = 256

# Regex to strip control characters (excluding common whitespace)
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def _sanitize_dep_field(value: str, max_length: int = _MAX_DEP_FIELD_LENGTH) -> str:
    """Sanitize a dependency field value before injecting into an LLM prompt.

    Strips control characters and truncates to a safe length to mitigate
    prompt injection from untrusted build file content.
    """
    sanitized = _CONTROL_CHAR_RE.sub("", value)
    return sanitized[:max_length]


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
            f"- {_sanitize_dep_field(dep.name)}: currently at {_sanitize_dep_field(dep.current_version)} ({_sanitize_dep_field(dep.description)})"
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

    async def identify_artifacts(
        self,
        project_files: dict[str, str],
        project_type: str,
    ) -> dict[str, list[str] | str]:
        """
        Identify build artifact directories and file patterns to exclude.

        Uses LLM reasoning about project structure to determine which
        directories and file patterns should be excluded from processing.
        """
        directories = set()
        structure_summary = []

        for file_path in project_files:
            directories.add(os.path.dirname(file_path))
            if len(structure_summary) < _MAX_STRUCTURE_SUMMARY:
                structure_summary.append(file_path)

        directory_list = sorted(directories)[:_MAX_DIRECTORIES]

        prompt = f"""Analyze this {project_type} project structure and identify build artifacts to exclude.

Top directories:
{json.dumps(directory_list, indent=2)}

Sample files ({len(structure_summary)} of {len(project_files)} total):
{json.dumps(structure_summary, indent=2)}

Identify directories and file patterns that are build artifacts, temporary files,
or generated content that should NOT be included in dependency analysis.

Return ONLY a JSON object:
{{
  "exclude_directories": ["dir1", "dir2"],
  "exclude_file_patterns": ["*.class", "*.jar"],
  "reasoning": "Brief explanation of why these were excluded"
}}"""

        try:
            result = await self.agent.run(
                task=TaskType.MANIFEST_PARSE,
                prompt=prompt,
                system=SYSTEM_PROMPT,
            )

            json_str = self._extract_json(result.content)
            exclusions = json.loads(json_str)

            if isinstance(exclusions, dict):
                return {
                    "directories": exclusions.get("exclude_directories", []),
                    "patterns": exclusions.get("exclude_file_patterns", []),
                    "reasoning": exclusions.get("reasoning", "No reasoning provided"),
                }
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse artifact analysis: {e}")

        return ArtifactExclusionConfig.get_fallback_exclusions("analysis error")

    async def update_dependency_file(
        self,
        project_type: str,
        file_content: str,
        dependencies: list[Dependency],
        file_name: str,
    ) -> str:
        """
        Rewrite a dependency file with updated versions.

        Returns the complete updated file content as a string.
        """
        updates = []
        for dep in dependencies:
            if dep.current_version != dep.latest_version:
                updates.append(
                    f"- {dep.name}: {dep.current_version} → {dep.latest_version}"
                )

        if not updates:
            return file_content

        prompt = f"""Update this {project_type} dependency file ({file_name}) with the following version changes:

{chr(10).join(updates)}

Current file content:
```
{file_content}
```

Return ONLY the complete updated file content. Do not include any explanation,
markdown fences, or surrounding text — just the raw file content ready to write to disk."""

        result = await self.agent.run(
            task=TaskType.CODE_UPDATE,
            prompt=prompt,
            system=SYSTEM_PROMPT,
        )

        return self._strip_code_fences(result.content)

    async def update_project(
        self,
        project_type: str,
        project_files: dict[str, str],
        dependencies: list[Dependency],
        dep_file_name: str,
        user_instructions: str = "",
    ) -> dict[str, str]:
        """
        Update an entire project after dependency version changes.

        First updates the dependency file, then analyzes source files for
        compatibility issues and applies fixes.

        Returns a dict mapping file paths to their updated content.
        """
        dep_file_content = project_files.get(dep_file_name, "")
        updated_dep_content = await self.update_dependency_file(
            project_type, dep_file_content, dependencies, dep_file_name
        )

        changes = []
        for dep in dependencies:
            if dep.current_version != dep.latest_version:
                changes.append(
                    f"{dep.name}: {dep.current_version} → {dep.latest_version}"
                )

        if not changes:
            return {dep_file_name: updated_dep_content}

        analyzable_files = self._filter_analyzable_files(project_files)

        files_content = "\n".join(
            f"=== {path} ===\n{content}"
            for path, content in analyzable_files.items()
        ) if analyzable_files else "# No analyzable source files found"

        instructions_block = ""
        if user_instructions:
            instructions_block = f"\n\nUser instructions:\n{user_instructions}"

        prompt = f"""A {project_type} project has these dependency version changes:

{chr(10).join(changes)}

Update ALL affected source files for compatibility with the new versions.
Fix any breaking API changes, deprecated method calls, or import changes.{instructions_block}

Project source files:
{files_content}

Return ONLY a JSON object mapping file paths to their complete updated content:
{{
  "path/to/file.ext": "complete updated file content...",
  "another/file.ext": "complete updated content..."
}}

Only include files that actually need changes. The dependency file ({dep_file_name})
has already been updated separately."""

        try:
            result = await self.agent.run(
                task=TaskType.CODE_UPDATE,
                prompt=prompt,
                system=SYSTEM_PROMPT,
            )

            json_str = self._extract_json(result.content)
            updated_files = json.loads(json_str)

            if not isinstance(updated_files, dict):
                updated_files = {}
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse project update response: {e}")
            updated_files = {}

        if dep_file_name not in updated_files:
            updated_files[dep_file_name] = updated_dep_content

        return updated_files

    async def analyze_security(
        self,
        dependencies: list[Dependency],
        project_type: str,
    ) -> dict:
        """Analyze dependencies for known security vulnerabilities."""
        dep_list = "\n".join(
            f"- {_sanitize_dep_field(dep.name)}@{_sanitize_dep_field(dep.current_version)}" for dep in dependencies
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

    # --- Private helpers ---

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

    def _filter_analyzable_files(self, project_files: dict[str, str]) -> dict[str, str]:
        """Filter project files to only those worth analyzing for code compatibility."""
        analyzable = {}
        for file_path, content in project_files.items():
            if not isinstance(content, str):
                continue
            if any(seg in file_path for seg in _EXCLUDED_PATH_SEGMENTS):
                continue
            if any(file_path.endswith(ext) for ext in _ANALYZABLE_EXTENSIONS):
                analyzable[file_path] = content

        if len(analyzable) > _MAX_PRIORITY_FILES:
            priority = {
                k: v for k, v in analyzable.items()
                if any(k.endswith(ext) for ext in (".scala", ".java", ".py", ".sbt", ".gradle"))
            }
            return dict(list(priority.items())[:_MAX_PRIORITY_FILES])

        return analyzable

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
        if content.startswith(("{", "[")):
            return content

        if "```json" in content:
            content = content.split("```json", 1)[1]
            content = content.split("```", 1)[0]
            return content.strip()
        if "```" in content:
            content = content.split("```", 1)[1]
            content = content.split("```", 1)[0]
            return content.strip()

        for i, char in enumerate(content):
            if char in ("{", "["):
                return content[i:]

        return content

    def _strip_code_fences(self, content: str) -> str:
        """Remove markdown code fences from generated file content."""
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[:-3]
        return content.strip()


# --- Sync wrappers for backward-compatible callers ---


_default_agent: DependencyAgent | None = None


def get_dependency_agent() -> DependencyAgent:
    """Get or create the singleton DependencyAgent."""
    global _default_agent
    if _default_agent is None:
        _default_agent = DependencyAgent()
    return _default_agent


def _run_sync(coro: Any) -> Any:
    """Run an async coroutine from a sync context safely."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=180)
    else:
        return asyncio.run(coro)


def research_latest_versions(
    dependencies: list[Dependency], project_type: str
) -> list[Dependency]:
    """Sync wrapper for DependencyAgent.research_latest_versions."""
    agent = get_dependency_agent()
    return _run_sync(agent.research_latest_versions(dependencies, project_type))


def extract_dependencies_with_gpt(
    project_type: str, file_content: str, file_name: str
) -> list[Dependency]:
    """Sync wrapper for DependencyAgent.extract_dependencies."""
    agent = get_dependency_agent()
    return _run_sync(agent.extract_dependencies(project_type, file_content, file_name))


def identify_artifacts_with_gpt(
    project_files: dict[str, str], project_type: str
) -> dict[str, list[str] | str]:
    """Sync wrapper for DependencyAgent.identify_artifacts."""
    agent = get_dependency_agent()
    return _run_sync(agent.identify_artifacts(project_files, project_type))


def update_dependency_file_with_gpt(
    project_type: str, file_content: str, dependencies: list[Dependency], file_name: str
) -> str:
    """Sync wrapper for DependencyAgent.update_dependency_file."""
    agent = get_dependency_agent()
    return _run_sync(
        agent.update_dependency_file(project_type, file_content, dependencies, file_name)
    )


def update_entire_project_with_gpt(
    project_type: str,
    project_files: dict[str, str],
    dependencies: list[Dependency],
    dep_file_name: str,
) -> dict[str, str]:
    """Sync wrapper for DependencyAgent.update_project."""
    agent = get_dependency_agent()
    return _run_sync(
        agent.update_project(project_type, project_files, dependencies, dep_file_name)
    )


def update_entire_project_with_gpt_with_progress(
    project_type: str,
    project_files: dict[str, str],
    dependencies: list[Dependency],
    dep_file_name: str,
    session_id: str,
    user_instructions: str = "",
) -> dict[str, str]:
    """Sync wrapper with progress tracking around the agent call."""
    from .progress_service import update_progress

    update_progress(
        session_id, "Updating dependency file", 20, f"Updating {dep_file_name} with new versions"
    )

    update_progress(
        session_id, "Analyzing code compatibility", 50,
        "AI is analyzing source files for breaking changes"
    )

    agent = get_dependency_agent()
    result = _run_sync(
        agent.update_project(
            project_type, project_files, dependencies, dep_file_name, user_instructions
        )
    )

    update_progress(
        session_id, "Processing results", 90, f"Applying {len(result)} file updates"
    )
    return result
