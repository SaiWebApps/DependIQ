"""
Tests for the LLM refactor: prompt templates, streaming agent, model tiering, events.

Covers:
- Prompt template loading and rendering (all 4 templates)
- Streaming agent yields correct event types in order
- New task types route to correct models
- Backward compatibility of existing run() method
- AnalysisEvent dataclass serialization
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm.agent import Agent, AgentResult
from app.services.llm.events import AnalysisEvent
from app.services.llm.prompts import TaskPromptManager
from app.services.llm.router import (
    COST_ROUTES,
    DEFAULT_ROUTES,
    LOCAL_ONLY_ROUTES,
    ModelRouter,
    RoutingMode,
    TaskType,
)
from app.services.llm.tools import ToolDefinition, ToolRegistry

# --- Helpers (reused from existing test_agent.py pattern) ---


def make_text_response(content: str, model: str = "test-model"):
    """Mock a litellm response with just text (no tool calls)."""
    message = MagicMock()
    message.content = content
    message.tool_calls = None
    message.model_dump.return_value = {"role": "assistant", "content": content}

    choice = MagicMock()
    choice.message = message

    response = MagicMock()
    response.choices = [choice]
    response.usage = MagicMock(total_tokens=100)
    return response


def make_tool_call_response(tool_name: str, arguments: dict, call_id: str = "call_1"):
    """Mock a litellm response that requests a tool call."""
    tool_call = MagicMock()
    tool_call.function.name = tool_name
    tool_call.function.arguments = json.dumps(arguments)
    tool_call.id = call_id

    message = MagicMock()
    message.content = None
    message.tool_calls = [tool_call]
    message.model_dump.return_value = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": tool_name, "arguments": json.dumps(arguments)},
            }
        ],
    }

    choice = MagicMock()
    choice.message = message

    response = MagicMock()
    response.choices = [choice]
    response.usage = MagicMock(total_tokens=50)
    return response


@pytest.fixture
def simple_registry():
    """A registry with one simple tool for testing."""
    registry = ToolRegistry()

    async def echo_tool(message: str = "hello") -> str:
        return f"Echo: {message}"

    registry.register(
        ToolDefinition(
            name="echo",
            description="Echoes a message",
            parameters={
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
            executor=echo_tool,
        )
    )
    return registry


@pytest.fixture
def agent(simple_registry, monkeypatch):
    """Agent with mocked router and simple tools."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    router = ModelRouter(mode=RoutingMode.QUALITY)
    return Agent(router=router, tools=simple_registry)


@pytest.fixture
def prompt_manager():
    """TaskPromptManager pointed at the real templates directory."""
    # tests/llm/test_llm_refactor.py -> tests/llm -> tests -> project root
    template_dir = (
        Path(__file__).parent.parent.parent / "app" / "services" / "llm" / "prompts"
    )
    return TaskPromptManager(template_dir=template_dir)


# --- Test: Prompt templates load and render ---


class TestPromptTemplatesLoad:
    def test_all_four_templates_exist(self, prompt_manager):
        """All 4 task-specific templates must exist."""
        templates = prompt_manager.list_templates()
        assert "extract_dependencies" in templates
        assert "map_architecture" in templates
        assert "explain_project" in templates
        assert "trace_chain_reaction" in templates

    def test_extract_dependencies_renders(self, prompt_manager):
        """extract_dependencies template renders with required variables."""
        result = prompt_manager.render(
            "extract_dependencies",
            project_type="python",
            file_name="requirements.txt",
            file_content="flask==2.3.0\nrequests>=2.28",
        )
        assert "python" in result
        assert "requirements.txt" in result
        assert "flask==2.3.0" in result
        assert "JSON" in result

    def test_map_architecture_renders(self, prompt_manager):
        """map_architecture template renders with project list."""
        projects = [
            {
                "name": "api-server",
                "dependencies": ["flask", "redis"],
                "imports": ["redis"],
            },
            {
                "name": "worker",
                "dependencies": ["celery", "redis"],
                "imports": ["celery"],
            },
        ]
        result = prompt_manager.render("map_architecture", projects=projects)
        assert "api-server" in result
        assert "worker" in result
        assert "relationship_type" in result

    def test_explain_project_renders(self, prompt_manager):
        """explain_project template renders with project info."""
        result = prompt_manager.render(
            "explain_project",
            project_name="my-api",
            file_tree="src/\n  main.py\n  routes/",
            dependencies=["flask", "sqlalchemy"],
            readme_excerpt="A REST API for managing widgets.",
        )
        assert "my-api" in result
        assert "flask" in result
        assert "primary_purpose" in result

    def test_trace_chain_reaction_renders(self, prompt_manager):
        """trace_chain_reaction template renders with trigger and projects."""
        projects = [
            {
                "name": "service-a",
                "pinned_version": "1.0.0",
                "other_deps": ["requests"],
                "usage_context": "Uses flask.Blueprint",
            }
        ]
        result = prompt_manager.render(
            "trace_chain_reaction",
            package_name="flask",
            current_version="2.3.0",
            new_version="3.0.0",
            breaking_changes=["Blueprint API changed", "Removed flask.ext"],
            projects=projects,
        )
        assert "flask" in result
        assert "3.0.0" in result
        assert "service-a" in result
        assert "severity" in result

    def test_nonexistent_template_returns_generic(self, prompt_manager):
        """A missing template returns the generic system prompt."""
        result = prompt_manager.render("nonexistent_task")
        assert "DependIQ" in result
        assert "dependency intelligence" in result

    def test_has_template_true(self, prompt_manager):
        """has_template returns True for existing templates."""
        assert prompt_manager.has_template("extract_dependencies")
        assert prompt_manager.has_template("map_architecture")

    def test_has_template_false(self, prompt_manager):
        """has_template returns False for missing templates."""
        assert not prompt_manager.has_template("does_not_exist")


# --- Test: Streaming agent yields events ---


class TestStreamingAgentYieldsEvents:
    @pytest.mark.asyncio
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_simple_response_event_sequence(self, mock_completion, agent):
        """Streaming yields progress -> thinking -> progress(complete) -> result."""
        mock_completion.return_value = make_text_response("Analysis complete: v3.1.0")

        events = []
        async for event in agent.run_streaming(
            task=TaskType.VERSION_RESEARCH,
            prompt="Check Flask version",
        ):
            events.append(event)

        # Verify event types in order
        event_types = [e.type for e in events]
        assert event_types[0] == "progress"  # starting
        assert "thinking" in event_types
        assert event_types[-2] == "progress"  # complete
        assert event_types[-1] == "result"

        # Verify content of key events
        progress_start = events[0]
        assert progress_start.phase == "starting"
        assert progress_start.pct == 0

        result_event = events[-1]
        assert result_event.data["content"] == "Analysis complete: v3.1.0"
        assert result_event.data["tool_calls_made"] == 0

    @pytest.mark.asyncio
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_tool_call_events(self, mock_completion, agent):
        """Streaming yields tool_call and tool_result events."""
        mock_completion.side_effect = [
            make_tool_call_response("echo", {"message": "test"}),
            make_text_response("Done"),
        ]

        events = []
        async for event in agent.run_streaming(
            task=TaskType.VERSION_RESEARCH,
            prompt="Echo test",
        ):
            events.append(event)

        event_types = [e.type for e in events]
        assert "tool_call" in event_types
        assert "tool_result" in event_types

        tool_call_event = next(e for e in events if e.type == "tool_call")
        assert tool_call_event.name == "echo"
        assert tool_call_event.input == {"message": "test"}

        tool_result_event = next(e for e in events if e.type == "tool_result")
        assert tool_result_event.name == "echo"
        assert "Echo: test" in tool_result_event.output

    @pytest.mark.asyncio
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_max_iterations_event(self, mock_completion, agent):
        """Streaming yields result with max_iterations message when limit hit."""
        agent.max_iterations = 2
        mock_completion.return_value = make_tool_call_response(
            "echo", {"message": "loop"}
        )

        events = []
        async for event in agent.run_streaming(
            task=TaskType.VERSION_RESEARCH,
            prompt="Loop forever",
        ):
            events.append(event)

        result_event = events[-1]
        assert result_event.type == "result"
        assert "Max iterations" in result_event.data["content"]

        # Should have progress(max_iterations) before result
        progress_events = [e for e in events if e.type == "progress"]
        last_progress = progress_events[-1]
        assert last_progress.phase == "max_iterations"

    @pytest.mark.asyncio
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_progress_pct_increases(self, mock_completion, agent):
        """Progress percentages should increase over iterations."""
        mock_completion.side_effect = [
            make_tool_call_response("echo", {"message": "1"}, "call_1"),
            make_tool_call_response("echo", {"message": "2"}, "call_2"),
            make_text_response("Done"),
        ]

        events = []
        async for event in agent.run_streaming(
            task=TaskType.VERSION_RESEARCH,
            prompt="Multi step",
        ):
            events.append(event)

        progress_events = [
            e for e in events if e.type == "progress" and e.pct is not None
        ]
        pcts = [e.pct for e in progress_events]
        # First is 0 (starting), then increasing, then 100 (complete)
        assert pcts[0] == 0
        assert pcts[-1] == 100


# --- Test: Router new task types ---


class TestRouterNewTaskTypes:
    def test_architecture_map_routes_to_sonnet(self):
        """ARCHITECTURE_MAP should route to Sonnet in quality mode."""
        router = ModelRouter(mode=RoutingMode.QUALITY)
        primary = router.get_primary_model(TaskType.ARCHITECTURE_MAP)
        assert "sonnet" in primary

    def test_project_summary_routes_to_haiku(self):
        """PROJECT_SUMMARY should route to Haiku in quality mode."""
        router = ModelRouter(mode=RoutingMode.QUALITY)
        primary = router.get_primary_model(TaskType.PROJECT_SUMMARY)
        assert "haiku" in primary

    def test_chain_reaction_routes_to_opus(self):
        """CHAIN_REACTION should route to Opus in quality mode."""
        router = ModelRouter(mode=RoutingMode.QUALITY)
        primary = router.get_primary_model(TaskType.CHAIN_REACTION)
        assert "opus" in primary

    def test_chain_reaction_opus_model_id(self):
        """CHAIN_REACTION primary should be the exact Opus model ID."""
        chain = DEFAULT_ROUTES[TaskType.CHAIN_REACTION]
        assert chain[0] == "anthropic/claude-opus-4-20250514"

    def test_relationship_detect_routes_to_sonnet(self):
        """RELATIONSHIP_DETECT should route to Sonnet in quality mode."""
        router = ModelRouter(mode=RoutingMode.QUALITY)
        primary = router.get_primary_model(TaskType.RELATIONSHIP_DETECT)
        assert "sonnet" in primary

    def test_new_tasks_in_all_route_tables(self):
        """All new task types must exist in DEFAULT, LOCAL_ONLY, and COST route tables."""
        new_tasks = [
            TaskType.ARCHITECTURE_MAP,
            TaskType.PROJECT_SUMMARY,
            TaskType.CHAIN_REACTION,
            TaskType.RELATIONSHIP_DETECT,
        ]
        for task in new_tasks:
            assert task in DEFAULT_ROUTES, f"{task} missing from DEFAULT_ROUTES"
            assert task in LOCAL_ONLY_ROUTES, f"{task} missing from LOCAL_ONLY_ROUTES"
            assert task in COST_ROUTES, f"{task} missing from COST_ROUTES"

    def test_new_tasks_local_only_uses_ollama(self):
        """New task types in LOCAL_ONLY mode should only use ollama models."""
        router = ModelRouter(mode=RoutingMode.LOCAL_ONLY)
        new_tasks = [
            TaskType.ARCHITECTURE_MAP,
            TaskType.PROJECT_SUMMARY,
            TaskType.CHAIN_REACTION,
            TaskType.RELATIONSHIP_DETECT,
        ]
        for task in new_tasks:
            chain = router.get_model_chain(task)
            for model in chain:
                assert model.startswith("ollama/"), (
                    f"Local-only mode for {task} should only use ollama, got {model}"
                )

    def test_cost_mode_chain_reaction_cheaper(self):
        """In cost mode, CHAIN_REACTION should prefer Sonnet over Opus."""
        chain = COST_ROUTES[TaskType.CHAIN_REACTION]
        assert "sonnet" in chain[0]

    def test_max_tokens_new_tasks(self):
        """New tasks should have appropriate max_tokens."""
        router = ModelRouter(mode=RoutingMode.BALANCED)
        # Heavy tasks get 8192
        assert router._max_tokens_for_task(TaskType.CHAIN_REACTION) == 8192
        assert router._max_tokens_for_task(TaskType.ARCHITECTURE_MAP) == 8192
        # Medium tasks get 4096
        assert router._max_tokens_for_task(TaskType.RELATIONSHIP_DETECT) == 4096
        # Light tasks get 2048
        assert router._max_tokens_for_task(TaskType.PROJECT_SUMMARY) == 2048


# --- Test: Backward compatibility of run() ---


class TestBackwardCompatRun:
    @pytest.mark.asyncio
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_run_returns_agent_result(self, mock_completion, agent):
        """run() still returns an AgentResult (not events)."""
        mock_completion.return_value = make_text_response("Version is 2.0.0")

        result = await agent.run(
            task=TaskType.VERSION_RESEARCH,
            prompt="What version?",
            system="You are a helper.",
        )

        assert isinstance(result, AgentResult)
        assert result.content == "Version is 2.0.0"
        assert result.model_used is not None
        assert result.tool_calls_made == 0
        assert result.total_tokens == 100

    @pytest.mark.asyncio
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_run_with_tools_still_works(self, mock_completion, agent):
        """run() still handles tool calls and returns final text."""
        mock_completion.side_effect = [
            make_tool_call_response("echo", {"message": "hi"}),
            make_text_response("Echo said hi"),
        ]

        result = await agent.run(
            task=TaskType.MANIFEST_PARSE,
            prompt="Say hi",
        )

        assert result.content == "Echo said hi"
        assert result.tool_calls_made == 1

    @pytest.mark.asyncio
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_run_simple_still_returns_string(self, mock_completion, agent):
        """run_simple() convenience method still works."""
        mock_completion.return_value = make_text_response("Just text")

        result = await agent.run_simple(task=TaskType.MANIFEST_PARSE, prompt="test")

        assert result == "Just text"
        assert isinstance(result, str)

    @pytest.mark.asyncio
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_existing_task_types_unchanged(self, mock_completion, agent):
        """Original task types still route correctly."""
        mock_completion.return_value = make_text_response("ok")

        # These should all work without errors
        for task in [
            TaskType.MANIFEST_PARSE,
            TaskType.DEPENDENCY_EXTRACT,
            TaskType.VERSION_RESEARCH,
            TaskType.CHANGELOG_SUMMARY,
            TaskType.SECURITY_ANALYSIS,
            TaskType.MIGRATION_PLANNING,
            TaskType.CODE_UPDATE,
        ]:
            result = await agent.run(task=task, prompt="test")
            assert result.content == "ok"


# --- Test: AnalysisEvent dataclass ---


class TestAnalysisEvent:
    def test_thinking_event_creation(self):
        """AnalysisEvent for thinking has correct fields."""
        event = AnalysisEvent(type="thinking", content="Analyzing dependencies...")
        assert event.type == "thinking"
        assert event.content == "Analyzing dependencies..."
        assert event.name is None
        assert event.data is None

    def test_tool_call_event_creation(self):
        """AnalysisEvent for tool_call has name and input."""
        event = AnalysisEvent(
            type="tool_call",
            name="fetch_package_versions",
            input={"packages": [{"name": "flask", "ecosystem": "pypi"}]},
        )
        assert event.type == "tool_call"
        assert event.name == "fetch_package_versions"
        assert event.input["packages"][0]["name"] == "flask"

    def test_tool_result_event_creation(self):
        """AnalysisEvent for tool_result has name and output."""
        event = AnalysisEvent(
            type="tool_result",
            name="fetch_package_versions",
            output='{"info": {"version": "3.0.0"}}',
        )
        assert event.type == "tool_result"
        assert event.name == "fetch_package_versions"
        assert "3.0.0" in event.output

    def test_progress_event_creation(self):
        """AnalysisEvent for progress has phase and pct."""
        event = AnalysisEvent(type="progress", phase="researching", pct=45)
        assert event.type == "progress"
        assert event.phase == "researching"
        assert event.pct == 45

    def test_result_event_creation(self):
        """AnalysisEvent for result has data dict."""
        event = AnalysisEvent(
            type="result",
            data={
                "content": "done",
                "model_used": "anthropic/claude-sonnet-4-20250514",
            },
        )
        assert event.type == "result"
        assert event.data["content"] == "done"

    def test_to_dict_omits_none_fields(self):
        """to_dict() should omit None fields for clean serialization."""
        event = AnalysisEvent(type="thinking", content="hello")
        d = event.to_dict()
        assert "type" in d
        assert "content" in d
        assert "name" not in d
        assert "input" not in d
        assert "output" not in d
        assert "phase" not in d
        assert "pct" not in d
        assert "data" not in d

    def test_to_dict_full_event(self):
        """to_dict() includes all non-None fields."""
        event = AnalysisEvent(
            type="tool_call",
            name="echo",
            input={"msg": "hi"},
        )
        d = event.to_dict()
        assert d == {"type": "tool_call", "name": "echo", "input": {"msg": "hi"}}

    def test_to_dict_is_json_serializable(self):
        """to_dict() output should be JSON-serializable."""
        event = AnalysisEvent(
            type="result",
            data={"versions": {"flask": "3.0.0"}},
        )
        serialized = json.dumps(event.to_dict())
        assert '"flask"' in serialized
        assert '"3.0.0"' in serialized
