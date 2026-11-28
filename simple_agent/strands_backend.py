"""Adapt the Strands model, callbacks, and failures to conversation contracts."""

import json
from collections.abc import Callable, Iterator
from copy import deepcopy
from urllib.parse import urlsplit

from strands.models.openai import OpenAIModel
from strands.types.content import Messages

from .conversation import (
    ConversationEvent,
    InvocationError,
    SessionDetails,
    TextDelta,
    TokenUsage,
    ToolCall,
    ToolResult,
    ToolSpec,
)
from .preferences import DEFAULT_AGENT_NAME, AgentPreferences, apply_preferences, normalize_agent_name
from .prompts import SYSTEM_PROMPT


_USAGE_FIELDS = (
    ("inputTokens", "input"),
    ("cacheReadInputTokens", "cache_read"),
    ("outputTokens", "output"),
)


class LocalOpenAIModel(OpenAIModel):
    @classmethod
    def format_request_messages(
        cls,
        messages: Messages,
        system_prompt: str | None = None,
        **kwargs,
    ) -> list[dict]:
        # Chat Completions omits past reasoning. Keep it in the agent's history.
        request_messages: Messages = [
            {
                **message,
                "content": [block for block in message["content"] if "reasoningContent" not in block],
            }
            for message in messages
        ]
        return super().format_request_messages(request_messages, system_prompt, **kwargs)


def invocation_error(error: Exception) -> InvocationError:
    status = getattr(error, "status_code", None)
    cause = getattr(error, "__cause__", None)
    name = type(error).__name__
    if isinstance(error, TimeoutError) or name == "APITimeoutError":
        message = "Provider timed out"
    elif isinstance(status, int):
        message = f"Provider request failed (HTTP {status})"
    elif (
        isinstance(error, ConnectionError)
        or isinstance(cause, ConnectionError)
        or name == "APIConnectionError"
    ):
        message = "Could not connect to model server"
    else:
        message = "The response failed. Try again."
    return InvocationError(f"{name}: {message}")


def _tool_result_parts(blocks: list[dict]) -> Iterator[str]:
    for block in blocks:
        if "text" in block:
            yield str(block["text"])
        elif "json" in block:
            yield json.dumps(block["json"], ensure_ascii=False)
        else:
            yield f"[{next(iter(block), 'content')}]"


def _events(event: dict) -> Iterator[ConversationEvent]:
    for key, reasoning in (("reasoningText", True), ("data", False)):
        if isinstance(chunk := event.get(key), str) and chunk:
            yield TextDelta(chunk, reasoning)
    message = event.get("message")
    if not isinstance(message, dict):
        return
    usage = (message.get("metadata") or {}).get("usage") or {}
    # Strands supplies zero input and output defaults when usage is absent.
    if (
        usage.get("inputTokens")
        or usage.get("outputTokens")
        or usage.get("cacheReadInputTokens") is not None
    ):
        counts = {
            label: count
            for key, label in _USAGE_FIELDS
            if type(count := usage.get(key)) is int and count >= 0
        }
        if counts:
            yield TokenUsage(counts)
    for block in message.get("content", []):
        if call := block.get("toolUse"):
            yield ToolCall(call.get("toolUseId", ""), call.get("name", "tool"), call.get("input"))
        elif result := block.get("toolResult"):
            yield ToolResult(
                result.get("toolUseId", ""),
                tuple(_tool_result_parts(result.get("content", []))),
                result.get("status") == "error",
            )


def strands_callback(emit: Callable[[ConversationEvent], None]) -> Callable[..., None]:
    def callback(**event) -> None:
        for item in _events(event):
            emit(item)

    return callback


class StrandsBackend:
    def __init__(self, agent):
        self._agent = agent

    def apply(self, preferences: AgentPreferences) -> None:
        apply_preferences(self._agent, preferences)

    def set_reasoning(self, enabled: bool) -> None:
        model = getattr(self._agent, "model", None)
        if not isinstance(model, OpenAIModel):
            return
        params = dict(model.get_config().get("params") or {})
        extra_body = dict(params.get("extra_body") or {})
        template_kwargs = dict(extra_body.get("chat_template_kwargs") or {})
        template_kwargs["enable_thinking"] = enabled
        extra_body["chat_template_kwargs"] = template_kwargs
        params["extra_body"] = extra_body
        model.update_config(params=params)

    def observe(self, emit: Callable[[ConversationEvent], None]) -> None:
        self._agent.callback_handler = strands_callback(emit)

    def details(self) -> SessionDetails:
        model = getattr(self._agent, "model", None)
        provider = getattr(self._agent, "provider_name", None)
        if not provider:
            provider = "OpenAI-compatible" if isinstance(model, OpenAIModel) else "unknown"
        try:
            model_id = model.get_config().get("model_id")
        except Exception:
            model_id = None
        base_url = (getattr(model, "client_args", None) or {}).get("base_url")
        endpoint = None
        if base_url:
            try:
                parts = urlsplit(base_url)
            except ValueError:
                pass
            else:
                endpoint = parts.netloc.rsplit("@", 1)[-1] + parts.path.rstrip("/")
        return SessionDetails(
            name=normalize_agent_name(getattr(self._agent, "name", None)) or DEFAULT_AGENT_NAME,
            system_prompt=getattr(self._agent, "system_prompt", SYSTEM_PROMPT) or "",
            provider=provider,
            model=model_id,
            endpoint=endpoint,
        )

    def tools(self) -> list[ToolSpec]:
        registry = getattr(self._agent, "tool_registry", None)
        return [
            ToolSpec(spec["name"], spec.get("description", "").partition("\n")[0])
            for spec in (registry.get_all_tool_specs() if registry is not None else ())
        ]

    def total_tokens(self) -> int:
        try:
            return int(self._agent.event_loop_metrics.accumulated_usage.get("totalTokens", 0))
        except Exception:
            return 0

    def checkpoint(self) -> object:
        return deepcopy(getattr(self._agent, "messages", None))

    def restore(self, checkpoint: object) -> None:
        if isinstance(checkpoint, list):
            self._agent.messages[:] = checkpoint

    def invoke(self, prompt: str) -> None:
        try:
            self._agent(prompt)
        except Exception as error:
            raise invocation_error(error) from error

    async def invoke_async(self, prompt: str) -> None:
        try:
            await self._agent.invoke_async(prompt)
        except Exception as error:
            raise invocation_error(error) from error
