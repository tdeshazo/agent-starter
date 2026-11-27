"""Wire the local model, system prompt, and application tools together."""
import os
from collections.abc import Callable, Mapping

from strands import Agent
from strands.models.openai import OpenAIModel

from .config import MODEL_HOST, MODEL_ID, model_port
from .conversation import Conversation
from .preferences import DEFAULT_AGENT_NAME, UserPreferences
from .prompts import SYSTEM_PROMPT
from .strands_backend import StrandsBackend, invocation_error
from .tools import DEFAULT_TOOLS


def resolve_base_url(env: Mapping[str, str] | None = None) -> str:
    """Resolve the OpenAI-compatible base URL from environment overrides."""
    source = os.environ if env is None else env
    if base_url := source.get("AGENT_BASE_URL"):
        return base_url
    return f"http://{MODEL_HOST}:{model_port(source)}/v1"


def create_agent() -> Agent:
    """Create a fresh agent with its own conversation history."""
    model = OpenAIModel(
        client_args={
            "base_url": resolve_base_url(),
            "api_key": "local",
            "timeout": 180.0,
            "max_retries": 0,
        },
        model_id=MODEL_ID,
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



def create_conversation(
    agent_factory: Callable[[], object],
    preferences: UserPreferences,
    *,
    agent=None,
) -> Conversation:
    def backend_factory() -> StrandsBackend:
        try:
            return StrandsBackend(agent_factory())
        except Exception as error:
            raise invocation_error(error) from error

    return Conversation(
        backend_factory,
        preferences,
        initial_backend=StrandsBackend(agent) if agent is not None else None,
    )
