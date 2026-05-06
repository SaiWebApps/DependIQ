"""
Tests for the DependencyAgent — the DependIQ-specific agent wrapper.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.models.dependency import Dependency
from app.services.dependency_agent import DependencyAgent
from app.services.llm.agent import AgentResult


@pytest.fixture
def dep_agent():
    return DependencyAgent()


class TestResearchLatestVersions:
    @pytest.mark.asyncio
    @patch.object(DependencyAgent, "_parse_version_response")
    async def test_calls_agent_with_correct_ecosystem(self, mock_parse, dep_agent):
        """Verify the prompt includes the correct ecosystem for the project type."""
        mock_parse.return_value = {"flask": "3.1.0"}

        with patch.object(dep_agent.agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = AgentResult(
                content='{"flask": "3.1.0"}',
                model_used="test",
                tool_calls_made=1,
            )

            deps = [Dependency(name="flask", current_version="2.0.0")]
            await dep_agent.research_latest_versions(deps, "python")

            call_kwargs = mock_run.call_args.kwargs
            assert "pypi" in call_kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_updates_dependency_versions(self, dep_agent):
        """Verify dependencies get their latest_version field updated."""
        with patch.object(dep_agent.agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = AgentResult(
                content='{"flask": "3.1.0", "requests": "2.32.0"}',
                model_used="anthropic/claude-sonnet-4-20250514",
                tool_calls_made=1,
            )

            deps = [
                Dependency(name="flask", current_version="2.0.0"),
                Dependency(name="requests", current_version="2.28.0"),
            ]
            result = await dep_agent.research_latest_versions(deps, "python")

            assert result[0].latest_version == "3.1.0"
            assert result[1].latest_version == "2.32.0"

    @pytest.mark.asyncio
    async def test_keeps_current_version_when_not_found(self, dep_agent):
        """If a dep isn't in the response, keep current version (don't crash)."""
        with patch.object(dep_agent.agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = AgentResult(
                content='{"flask": "3.1.0"}',
                model_used="test",
                tool_calls_made=1,
            )

            deps = [
                Dependency(name="flask", current_version="2.0.0"),
                Dependency(name="obscure-lib", current_version="1.0.0"),
            ]
            result = await dep_agent.research_latest_versions(deps, "python")

            assert result[0].latest_version == "3.1.0"
            assert result[1].latest_version == "1.0.0"

    @pytest.mark.asyncio
    async def test_empty_dependencies_returns_early(self, dep_agent):
        """Empty input should return immediately without calling the agent."""
        with patch.object(dep_agent.agent, "run", new_callable=AsyncMock) as mock_run:
            result = await dep_agent.research_latest_versions([], "python")
            assert result == []
            mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_maven_ecosystem_mapping(self, dep_agent):
        """Maven/Gradle/SBT projects should map to 'maven' ecosystem."""
        with patch.object(dep_agent.agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = AgentResult(
                content='{"spark-core": "3.5.1"}',
                model_used="test",
                tool_calls_made=1,
            )

            deps = [Dependency(name="spark-core", current_version="3.2.0")]

            for project_type in ["maven", "gradle", "sbt"]:
                await dep_agent.research_latest_versions(deps, project_type)
                call_kwargs = mock_run.call_args.kwargs
                assert "maven" in call_kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_handles_malformed_json_gracefully(self, dep_agent):
        """If agent returns garbage, don't crash — keep current versions."""
        with patch.object(dep_agent.agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = AgentResult(
                content="Sorry, I couldn't parse the results.",
                model_used="test",
                tool_calls_made=0,
            )

            deps = [Dependency(name="flask", current_version="2.0.0")]
            result = await dep_agent.research_latest_versions(deps, "python")

            assert result[0].latest_version == "2.0.0"

    @pytest.mark.asyncio
    async def test_handles_json_in_markdown_fences(self, dep_agent):
        """Agent might wrap JSON in ```json ... ``` fences."""
        with patch.object(dep_agent.agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = AgentResult(
                content='Here are the versions:\n```json\n{"flask": "3.1.0"}\n```',
                model_used="test",
                tool_calls_made=1,
            )

            deps = [Dependency(name="flask", current_version="2.0.0")]
            result = await dep_agent.research_latest_versions(deps, "python")

            assert result[0].latest_version == "3.1.0"


class TestExtractDependencies:
    @pytest.mark.asyncio
    async def test_extracts_from_requirements_txt(self, dep_agent):
        with patch.object(dep_agent.agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = AgentResult(
                content=json.dumps([
                    {"name": "flask", "current_version": "2.0.0", "description": "Web framework"},
                    {"name": "requests", "current_version": "2.28.0", "description": "HTTP library"},
                ]),
                model_used="test",
                tool_calls_made=0,
            )

            result = await dep_agent.extract_dependencies(
                "python", "flask==2.0.0\nrequests==2.28.0", "requirements.txt"
            )

            assert len(result) == 2
            assert result[0].name == "flask"
            assert result[0].current_version == "2.0.0"

    @pytest.mark.asyncio
    async def test_handles_empty_response(self, dep_agent):
        with patch.object(dep_agent.agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = AgentResult(
                content="[]", model_used="test", tool_calls_made=0
            )

            result = await dep_agent.extract_dependencies(
                "python", "", "requirements.txt"
            )
            assert result == []


class TestProjectTypeMapping:
    def test_python_maps_to_pypi(self, dep_agent):
        assert dep_agent._project_type_to_ecosystem("python") == "pypi"

    def test_sbt_maps_to_maven(self, dep_agent):
        assert dep_agent._project_type_to_ecosystem("sbt") == "maven"

    def test_gradle_maps_to_maven(self, dep_agent):
        assert dep_agent._project_type_to_ecosystem("gradle") == "maven"

    def test_unknown_defaults_to_pypi(self, dep_agent):
        assert dep_agent._project_type_to_ecosystem("unknown") == "pypi"

    def test_case_insensitive(self, dep_agent):
        assert dep_agent._project_type_to_ecosystem("Python") == "pypi"
        assert dep_agent._project_type_to_ecosystem("NPM") == "npm"


class TestExtractJson:
    def test_raw_json_object(self, dep_agent):
        assert dep_agent._extract_json('{"a": 1}') == '{"a": 1}'

    def test_raw_json_array(self, dep_agent):
        assert dep_agent._extract_json('[1, 2]') == '[1, 2]'

    def test_markdown_fenced(self, dep_agent):
        content = 'Here:\n```json\n{"a": 1}\n```\nDone'
        assert dep_agent._extract_json(content) == '{"a": 1}'

    def test_text_before_json(self, dep_agent):
        content = 'The result is: {"a": 1}'
        assert dep_agent._extract_json(content) == '{"a": 1}'

    def test_generic_code_fence(self, dep_agent):
        content = '```\n[1, 2, 3]\n```'
        assert dep_agent._extract_json(content) == '[1, 2, 3]'
