"""
Tests for the LLM agent loop.

These tests mock litellm.acompletion to verify the agent's behavior
without making real API calls.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm.agent import Agent, AgentResult
from app.services.llm.router import ModelRouter, RoutingMode, TaskType
from app.services.llm.tools import ToolDefinition, ToolRegistry

# --- Helpers to build mock litellm responses ---


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


# --- Test fixtures ---


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
    """Agent with mocked router (always uses test-model) and simple tools."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    router = ModelRouter(mode=RoutingMode.QUALITY)
    return Agent(router=router, tools=simple_registry)


# --- Tests ---


class TestAgentSimpleResponse:
    @pytest.mark.asyncio
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_direct_text_response(self, mock_completion, agent):
        """Agent returns text when LLM doesn't call any tools."""
        mock_completion.return_value = make_text_response("The latest version is 3.1.0")

        result = await agent.run(
            task=TaskType.VERSION_RESEARCH,
            prompt="What is the latest version of Flask?",
        )

        assert isinstance(result, AgentResult)
        assert result.content == "The latest version is 3.1.0"
        assert result.tool_calls_made == 0
        assert result.total_tokens == 100
        mock_completion.assert_called_once()

    @pytest.mark.asyncio
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_system_prompt_included(self, mock_completion, agent):
        """System prompt is passed to the LLM."""
        mock_completion.return_value = make_text_response("done")

        await agent.run(
            task=TaskType.MANIFEST_PARSE,
            prompt="Parse this",
            system="You are a dependency expert.",
        )

        call_kwargs = mock_completion.call_args.kwargs
        messages = call_kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a dependency expert."


class TestAgentToolUse:
    @pytest.mark.asyncio
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_single_tool_call(self, mock_completion, agent):
        """Agent executes tool and feeds result back to LLM."""
        # First call: LLM requests echo tool
        # Second call: LLM returns final text
        mock_completion.side_effect = [
            make_tool_call_response("echo", {"message": "world"}),
            make_text_response("Tool said: Echo: world"),
        ]

        result = await agent.run(
            task=TaskType.VERSION_RESEARCH,
            prompt="Echo world",
        )

        assert result.content == "Tool said: Echo: world"
        assert result.tool_calls_made == 1
        assert mock_completion.call_count == 2

        # Verify tool result was fed back
        second_call_messages = mock_completion.call_args_list[1].kwargs["messages"]
        tool_result_msg = [m for m in second_call_messages if m.get("role") == "tool"]
        assert len(tool_result_msg) == 1
        assert "Echo: world" in tool_result_msg[0]["content"]

    @pytest.mark.asyncio
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_multiple_tool_calls(self, mock_completion, agent):
        """Agent handles multiple rounds of tool calls."""
        mock_completion.side_effect = [
            make_tool_call_response("echo", {"message": "first"}, "call_1"),
            make_tool_call_response("echo", {"message": "second"}, "call_2"),
            make_text_response("Done after 2 tool calls"),
        ]

        result = await agent.run(task=TaskType.VERSION_RESEARCH, prompt="Do two things")

        assert result.tool_calls_made == 2
        assert result.content == "Done after 2 tool calls"
        assert mock_completion.call_count == 3

    @pytest.mark.asyncio
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_max_iterations_safety(self, mock_completion, agent):
        """Agent stops after max_iterations even if LLM keeps calling tools."""
        agent.max_iterations = 3
        mock_completion.return_value = make_tool_call_response(
            "echo", {"message": "loop"}
        )

        result = await agent.run(task=TaskType.VERSION_RESEARCH, prompt="Loop forever")

        assert "Max iterations" in result.content
        assert result.tool_calls_made == 3


class TestAgentFailover:
    @pytest.mark.asyncio
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_failover_on_error(self, mock_completion, agent, monkeypatch):
        """Agent falls back to next model when primary fails."""
        monkeypatch.setenv("OPENAI_API_KEY", "test")

        # First call fails, second succeeds
        mock_completion.side_effect = [
            Exception("Rate limited"),
            make_text_response("Fallback worked"),
        ]

        result = await agent.run(task=TaskType.VERSION_RESEARCH, prompt="test")

        assert result.content == "Fallback worked"
        assert mock_completion.call_count == 2

    @pytest.mark.asyncio
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_all_models_fail_raises(self, mock_completion, monkeypatch):
        """If all models in chain fail, exception propagates."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        # Only ollama as fallback, both fail
        router = ModelRouter(
            mode=RoutingMode.QUALITY,
            custom_routes={TaskType.MANIFEST_PARSE: ["anthropic/test", "ollama/test"]},
        )
        agent = Agent(router=router, tools=ToolRegistry())

        mock_completion.side_effect = Exception("All dead")

        with pytest.raises(Exception, match="All dead"):
            await agent.run(task=TaskType.MANIFEST_PARSE, prompt="test")


class TestAgentRunSimple:
    @pytest.mark.asyncio
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_run_simple_returns_string(self, mock_completion, agent):
        mock_completion.return_value = make_text_response("Just text")

        result = await agent.run_simple(task=TaskType.MANIFEST_PARSE, prompt="test")

        assert result == "Just text"
        assert isinstance(result, str)
