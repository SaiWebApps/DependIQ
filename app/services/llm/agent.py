"""
Provider-agnostic agentic loop.

Owns the tool_use conversation cycle: send message with tools → if LLM
calls a tool → execute it → feed result back → repeat until LLM stops.

Uses litellm as transport so any provider (Anthropic, OpenAI, Ollama, etc.)
works with the same code.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

import litellm

from .router import ModelRouter, TaskType
from .tools import ToolRegistry, create_default_registry

logger = logging.getLogger(__name__)

# Suppress litellm's noisy logging
litellm.suppress_debug_info = True
# Bypass corporate proxy for LLM API calls
os.environ.setdefault("no_proxy", os.environ.get("NO_PROXY", ""))
litellm.client_session = None
litellm.aclient_session = None


@dataclass
class AgentResult:
    """The final result of an agent run."""

    content: str
    model_used: str
    tool_calls_made: int
    total_tokens: int = 0


@dataclass
class Agent:
    """
    Provider-agnostic LLM agent with tool use.

    Usage:
        agent = Agent()
        result = await agent.run(
            task=TaskType.VERSION_RESEARCH,
            prompt="Check the latest versions of flask and requests on PyPI.",
        )
        print(result.content)
    """

    router: ModelRouter = field(default_factory=ModelRouter)
    tools: ToolRegistry = field(default_factory=create_default_registry)
    max_iterations: int = 10

    async def run(
        self,
        task: TaskType,
        prompt: str,
        system: str = "",
    ) -> AgentResult:
        """
        Run the agent loop for a given task.

        Args:
            task: What kind of work this is (determines model selection)
            prompt: The user prompt
            system: Optional system prompt

        Returns:
            AgentResult with the final text response
        """
        model_chain = self.router.filter_chain_by_available(task)
        if not model_chain:
            model_chain = self.router.get_model_chain(task)

        model = model_chain[0]
        fallbacks = model_chain[1:]
        config = self.router.get_config(task)

        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        tool_schemas = self.tools.schemas_openai()
        tool_calls_made = 0
        total_tokens = 0

        for iteration in range(self.max_iterations):
            try:
                response = await litellm.acompletion(
                    model=model,
                    messages=messages,
                    tools=tool_schemas if tool_schemas else None,
                    temperature=config["temperature"],
                    max_tokens=config["max_tokens"],
                )
            except Exception as e:
                if fallbacks:
                    logger.warning(f"Model {model} failed ({e}), trying fallback")
                    model = fallbacks.pop(0)
                    continue
                raise

            choice = response.choices[0]
            message = choice.message
            total_tokens += (
                getattr(response, "usage", None) and response.usage.total_tokens
            ) or 0

            if not message.tool_calls:
                return AgentResult(
                    content=message.content or "",
                    model_used=model,
                    tool_calls_made=tool_calls_made,
                    total_tokens=total_tokens,
                )

            messages.append(message.model_dump())

            for tool_call in message.tool_calls:
                fn_name = tool_call.function.name
                try:
                    fn_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    fn_args = {}

                logger.info(f"Tool call: {fn_name}({list(fn_args.keys())})")
                result = await self.tools.execute(fn_name, fn_args)
                tool_calls_made += 1

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    }
                )

        return AgentResult(
            content="Max iterations reached without final response.",
            model_used=model,
            tool_calls_made=tool_calls_made,
            total_tokens=total_tokens,
        )

    async def run_simple(
        self,
        task: TaskType,
        prompt: str,
        system: str = "",
    ) -> str:
        """Convenience method that returns just the content string."""
        result = await self.run(task=task, prompt=prompt, system=system)
        return result.content
