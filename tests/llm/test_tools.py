"""
Tests for the LLM tools module.

Tests the tool registry, schema generation, and actual HTTP-backed executors
against live registries (integration) and mocked responses (unit).
"""

import httpx
import pytest
import respx

from app.services.llm.tools import (
    REGISTRY_TEMPLATES,
    ToolDefinition,
    ToolRegistry,
    create_default_registry,
    fetch_package_versions,
    search_web,
    web_fetch,
)

# --- Unit tests: ToolRegistry ---


class TestToolRegistry:
    def test_register_and_get(self):
        registry = ToolRegistry()

        async def noop(**kwargs):
            return "ok"

        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {}},
            executor=noop,
        )
        registry.register(tool)

        assert registry.get("test_tool") is tool
        assert registry.get("nonexistent") is None

    def test_tool_names(self):
        registry = create_default_registry()
        assert "fetch_package_versions" in registry.tool_names
        assert "web_fetch" in registry.tool_names
        assert "search_web" in registry.tool_names

    def test_schemas_openai_format(self):
        registry = create_default_registry()
        schemas = registry.schemas_openai()

        assert len(schemas) == 3
        for schema in schemas:
            assert schema["type"] == "function"
            assert "function" in schema
            assert "name" in schema["function"]
            assert "description" in schema["function"]
            assert "parameters" in schema["function"]

    def test_schemas_anthropic_format(self):
        registry = create_default_registry()
        schemas = registry.schemas_anthropic()

        assert len(schemas) == 3
        for schema in schemas:
            assert "name" in schema
            assert "description" in schema
            assert "input_schema" in schema
            # Anthropic format does NOT have "type": "function" wrapper
            assert "type" not in schema

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        registry = ToolRegistry()
        result = await registry.execute("nonexistent", {})
        assert "Error: unknown tool" in result

    @pytest.mark.asyncio
    async def test_execute_tool_exception(self):
        async def exploding_tool(**kwargs):
            raise ValueError("boom")

        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="bomb",
                description="explodes",
                parameters={"type": "object", "properties": {}},
                executor=exploding_tool,
            )
        )
        result = await registry.execute("bomb", {})
        assert "Error executing bomb" in result
        assert "boom" in result


# --- Unit tests: fetch_package_versions with mocked HTTP ---


class TestFetchPackageVersionsMocked:
    @pytest.mark.asyncio
    @respx.mock
    async def test_pypi_success(self):
        respx.get("https://pypi.org/pypi/flask/json").mock(
            return_value=httpx.Response(
                200,
                json={"info": {"version": "3.1.0", "name": "Flask"}},
            )
        )

        result = await fetch_package_versions([{"name": "flask", "ecosystem": "pypi"}])
        assert "flask" in result
        assert "3.1.0" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_npm_success(self):
        respx.get("https://registry.npmjs.org/express").mock(
            return_value=httpx.Response(
                200,
                json={
                    "name": "express",
                    "dist-tags": {"latest": "4.21.0"},
                    "version": "4.21.0",
                },
            )
        )

        result = await fetch_package_versions([{"name": "express", "ecosystem": "npm"}])
        assert "express" in result
        assert "4.21.0" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_404_package(self):
        respx.get("https://pypi.org/pypi/nonexistent-pkg-xyz/json").mock(
            return_value=httpx.Response(404)
        )

        result = await fetch_package_versions(
            [{"name": "nonexistent-pkg-xyz", "ecosystem": "pypi"}]
        )
        assert "not found" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_timeout(self):
        respx.get("https://pypi.org/pypi/slow-pkg/json").mock(
            side_effect=httpx.TimeoutException("timed out")
        )

        result = await fetch_package_versions(
            [{"name": "slow-pkg", "ecosystem": "pypi"}]
        )
        assert "timeout" in result

    @pytest.mark.asyncio
    async def test_unsupported_ecosystem(self):
        result = await fetch_package_versions(
            [{"name": "something", "ecosystem": "unknown_registry"}]
        )
        assert "unsupported ecosystem" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_parallel_multiple_packages(self):
        respx.get("https://pypi.org/pypi/flask/json").mock(
            return_value=httpx.Response(200, json={"info": {"version": "3.1.0"}})
        )
        respx.get("https://pypi.org/pypi/requests/json").mock(
            return_value=httpx.Response(200, json={"info": {"version": "2.32.0"}})
        )
        respx.get("https://registry.npmjs.org/express").mock(
            return_value=httpx.Response(200, json={"version": "4.21.0"})
        )

        result = await fetch_package_versions(
            [
                {"name": "flask", "ecosystem": "pypi"},
                {"name": "requests", "ecosystem": "pypi"},
                {"name": "express", "ecosystem": "npm"},
            ]
        )
        assert "flask" in result
        assert "requests" in result
        assert "express" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_maven_with_group(self):
        respx.get(
            "https://search.maven.org/solrsearch/select?q=g:org.apache.spark+AND+a:spark-core&rows=1&wt=json"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"response": {"docs": [{"latestVersion": "3.5.1"}]}},
            )
        )

        result = await fetch_package_versions(
            [
                {
                    "name": "spark-core",
                    "ecosystem": "maven",
                    "group": "org.apache.spark",
                    "artifact": "spark-core",
                }
            ]
        )
        assert "spark-core" in result
        assert "3.5.1" in result


# --- Unit tests: web_fetch ---


class TestWebFetchMocked:
    @pytest.mark.asyncio
    @respx.mock
    async def test_success(self):
        respx.get("https://example.com/changelog").mock(
            return_value=httpx.Response(200, text="## v2.0.0\n- Breaking changes")
        )

        result = await web_fetch("https://example.com/changelog")
        assert "Breaking changes" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_error(self):
        respx.get("https://down.example.com").mock(
            side_effect=httpx.ConnectError("connection refused")
        )

        result = await web_fetch("https://down.example.com")
        assert "Error fetching" in result


# --- Unit tests: search_web ---


class TestSearchWeb:
    @pytest.mark.asyncio
    async def test_no_api_key(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        result = await search_web("flask migration guide")
        assert "unavailable" in result


# --- Integration tests: live registry calls ---


@pytest.mark.integration
class TestFetchPackageVersionsLive:
    """These hit real registries. Run with: pytest -m integration
    Note: PyPI may be blocked by corporate proxies. npm/crates typically work."""

    @pytest.mark.asyncio
    async def test_pypi_flask_live(self):
        result = await fetch_package_versions([{"name": "flask", "ecosystem": "pypi"}])
        assert "flask" in result
        if "403" in result or "Proxy" in result:
            pytest.skip("PyPI blocked by corporate proxy")
        assert "version" in result.lower()

    @pytest.mark.asyncio
    async def test_npm_express_live(self):
        result = await fetch_package_versions([{"name": "express", "ecosystem": "npm"}])
        assert "express" in result

    @pytest.mark.asyncio
    async def test_multiple_ecosystems_live(self):
        result = await fetch_package_versions(
            [
                {"name": "flask", "ecosystem": "pypi"},
                {"name": "express", "ecosystem": "npm"},
                {"name": "serde", "ecosystem": "crates"},
            ]
        )
        assert "flask" in result
        assert "express" in result
        assert "serde" in result


# --- Schema validation ---


class TestRegistryTemplates:
    def test_all_templates_have_package_placeholder(self):
        """Every template must have {package} or {group}/{artifact} for Maven."""
        for ecosystem, template in REGISTRY_TEMPLATES.items():
            if ecosystem == "maven":
                assert "{group}" in template and "{artifact}" in template
            else:
                assert "{package}" in template, (
                    f"{ecosystem} template missing {{package}}"
                )

    def test_all_templates_are_https(self):
        for ecosystem, template in REGISTRY_TEMPLATES.items():
            assert template.startswith("https://"), f"{ecosystem} template not HTTPS"
