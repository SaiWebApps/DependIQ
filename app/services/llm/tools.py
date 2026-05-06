"""
Tool definitions and executors for the DependIQ agent.

Design: The model NEVER constructs URLs. Registry URL templates are
hardcoded here. The model supplies only package names and ecosystems.
This prevents hallucinated endpoints while letting the LLM drive research.
"""

import asyncio
import os
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

import httpx

REGISTRY_TEMPLATES: dict[str, str] = {
    "pypi": "https://pypi.org/pypi/{package}/json",
    "npm": "https://registry.npmjs.org/{package}",
    "maven": "https://search.maven.org/solrsearch/select?q=g:{group}+AND+a:{artifact}&rows=1&wt=json",
    "rubygems": "https://rubygems.org/api/v1/gems/{package}.json",
    "crates": "https://crates.io/api/v1/crates/{package}",
    "nuget": "https://api.nuget.org/v3-flatcontainer/{package}/index.json",
    "hex": "https://hex.pm/api/packages/{package}",
    "packagist": "https://repo.packagist.org/p2/{package}.json",
    "pub": "https://pub.dev/api/packages/{package}",
    "go": "https://proxy.golang.org/{package}/@latest",
}

HEADERS = {
    "User-Agent": "DependIQ/1.0 (https://github.com/dependiq; dependency-intelligence-tool)",
    "Accept": "application/json",
}


@dataclass
class ToolDefinition:
    """A tool the agent can invoke."""

    name: str
    description: str
    parameters: dict[str, Any]
    executor: Callable[..., Coroutine[Any, Any, str]]


@dataclass
class ToolRegistry:
    """Registry of all tools available to the agent."""

    _tools: dict[str, ToolDefinition] = field(default_factory=dict)

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def schemas_openai(self) -> list[dict[str, Any]]:
        """Tool schemas in OpenAI function-calling format (de facto standard)."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
        ]

    def schemas_anthropic(self) -> list[dict[str, Any]]:
        """Tool schemas in Anthropic format."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.parameters,
            }
            for t in self._tools.values()
        ]

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        tool = self._tools.get(name)
        if not tool:
            return f"Error: unknown tool '{name}'"
        try:
            return await tool.executor(**arguments)
        except Exception as e:
            return f"Error executing {name}: {e}"


# --- Tool executors ---


async def fetch_package_versions(packages: list[dict[str, str]]) -> str:
    """
    Fetch version info for multiple packages in parallel.
    Model supplies package names + ecosystems. We construct URLs from templates.
    """
    async with httpx.AsyncClient(
        timeout=15, follow_redirects=True, headers=HEADERS, trust_env=False
    ) as client:

        async def fetch_one(pkg: dict[str, str]) -> str:
            ecosystem = pkg.get("ecosystem", "").lower()
            name = pkg.get("name", "")
            group = pkg.get("group", "")
            artifact = pkg.get("artifact", name)

            if ecosystem == "maven":
                resolved_group = group or (name.split(":")[0] if ":" in name else "")
                resolved_artifact = (
                    artifact
                    if artifact != name
                    else (name.split(":")[-1] if ":" in name else name)
                )
                url = REGISTRY_TEMPLATES["maven"].format(
                    group=resolved_group,
                    artifact=resolved_artifact,
                )
            elif ecosystem in REGISTRY_TEMPLATES:
                url = REGISTRY_TEMPLATES[ecosystem].format(package=name)
            else:
                return f"{name}: unsupported ecosystem '{ecosystem}'"

            try:
                resp = await client.get(url)
                if resp.status_code == 404:
                    return f"{name}: not found on {ecosystem}"
                if resp.status_code != 200:
                    return f"{name}: HTTP {resp.status_code} from {ecosystem}"
                return f"=== {name} ({ecosystem}) ===\n{resp.text[:4000]}"
            except httpx.TimeoutException:
                return f"{name}: timeout fetching from {ecosystem}"
            except Exception as e:
                return f"{name}: error - {e}"

        results = await asyncio.gather(
            *[fetch_one(p) for p in packages], return_exceptions=True
        )
        return "\n\n".join(
            str(r) if not isinstance(r, Exception) else f"Error: {r}" for r in results
        )


async def web_fetch(url: str) -> str:
    """Generic web fetch for changelogs, GitHub releases, advisories, etc."""
    async with httpx.AsyncClient(
        timeout=15, follow_redirects=True, headers=HEADERS, trust_env=False
    ) as client:
        try:
            resp = await client.get(url)
            return resp.text[:15000]
        except Exception as e:
            return f"Error fetching {url}: {e}"


async def search_web(query: str) -> str:
    """Web search via Tavily (if configured) for docs, migration guides, etc."""
    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key:
        return "Web search unavailable (TAVILY_API_KEY not set). Use fetch_package_versions or web_fetch instead."

    async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
        resp = await client.post(
            "https://api.tavily.com/search",
            json={"api_key": tavily_key, "query": query, "max_results": 5},
        )
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            return "\n\n".join(
                f"[{r['title']}]({r['url']})\n{r['content'][:500]}" for r in results
            )
        return f"Search failed: HTTP {resp.status_code}"


# --- Default registry factory ---


def create_default_registry() -> ToolRegistry:
    """Create the standard tool registry for DependIQ agents."""
    registry = ToolRegistry()

    registry.register(
        ToolDefinition(
            name="fetch_package_versions",
            description=(
                "Fetch latest version information for multiple packages from their "
                "official registries (PyPI, npm, Maven Central, crates.io, etc.) in parallel. "
                "You provide package names and ecosystems; the tool handles URL construction. "
                "Supported ecosystems: pypi, npm, maven, rubygems, crates, nuget, hex, packagist, pub, go."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "packages": {
                        "type": "array",
                        "description": "Packages to look up",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "Package name (e.g. 'flask', 'express')",
                                },
                                "ecosystem": {
                                    "type": "string",
                                    "enum": list(REGISTRY_TEMPLATES.keys()),
                                    "description": "Package registry",
                                },
                                "group": {
                                    "type": "string",
                                    "description": "Maven group ID (maven only)",
                                },
                                "artifact": {
                                    "type": "string",
                                    "description": "Maven artifact ID if different from name",
                                },
                            },
                            "required": ["name", "ecosystem"],
                        },
                    }
                },
                "required": ["packages"],
            },
            executor=fetch_package_versions,
        )
    )

    registry.register(
        ToolDefinition(
            name="web_fetch",
            description=(
                "Fetch content of any URL. Use for changelogs, GitHub releases, "
                "CVE databases, migration guides, or any web resource."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"}
                },
                "required": ["url"],
            },
            executor=web_fetch,
        )
    )

    registry.register(
        ToolDefinition(
            name="search_web",
            description=(
                "Search the web for documentation, migration guides, or compatibility info. "
                "Requires TAVILY_API_KEY. Prefer fetch_package_versions for version lookups."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"],
            },
            executor=search_web,
        )
    )

    return registry
