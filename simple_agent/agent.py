"""Wire the local model, system prompt, and application tools together."""
from collections.abc import Mapping
import os

from strands import Agent
from strands.models.openai import OpenAIModel

from .prompts import SYSTEM_PROMPT
from .settings import DEFAULT_AGENT_NAME
from .tools import DEFAULT_TOOLS


def resolve_base_url(env: Mapping[str, str] | None = None) -> str:
    """Resolve the OpenAI-compatible base URL from environment overrides."""
    source = os.environ if env is None else env
    if base_url := source.get("AGENT_BASE_URL"):
        return base_url
    port = source.get("AGENT_PORT") or "8088"
    return f"http://127.0.0.1:{port}/v1"


def create_agent() -> Agent:
    """Create a fresh agent with its own conversation history."""
    model = OpenAIModel(
        client_args={
            "base_url": resolve_base_url(),
            "api_key": "local",
            "timeout": 180.0,
            "max_retries": 0,
        },
        model_id="gemma-4-e4b",
        params={
            "max_tokens": 2048,
            "temperature": 0.2,
            "extra_body": {
                "cache_prompt": True,
                "chat_template_kwargs": {"enable_thinking": False},
            },
        },
    )
    return Agent(
        model=model,
        tools=list(DEFAULT_TOOLS),
        name=DEFAULT_AGENT_NAME,
        system_prompt=SYSTEM_PROMPT,
    )
