"""Describe slash commands and format local session information."""

from strands.models.openai import OpenAIModel

from .pets import PET_NAMES
from .session import session_model_id


COMMANDS = {
    "/clear": "start a new conversation with empty history",
    "/exit": "exit the agent",
    "/pet": f"choose a companion pet ({len(PET_NAMES)} available)",
    "/settings": "edit the agent name and system prompt",
    "/tools": "list the registered tools",
    "/status": "show the active provider and model ID",
}


def parse_pet_command(prompt: str) -> tuple[bool, str | None]:
    """Parse ``/pet`` or ``/pet <name>`` into ``(is_pet_command, arg)``."""
    parts = prompt.split(None, 1)
    if not parts or parts[0] != "/pet":
        return False, None
    return True, parts[1].strip() if len(parts) > 1 else None


def command_output(prompt: str, agent) -> str | None:
    """Return the transcript text for a read-only slash command."""
    if prompt == "/tools":
        registry = getattr(agent, "tool_registry", None)
        specs = registry.get_all_tool_specs() if registry is not None else ()
        lines = []
        for spec in specs:
            name = spec["name"]
            summary = spec.get("description", "").partition("\n")[0]
            lines.append(f"{name} — {summary}" if summary else name)
        return "\n".join(lines) or "No tools registered."
    if prompt == "/status":
        provider = getattr(agent, "provider_name", None)
        if not provider:
            model = getattr(agent, "model", None)
            provider = "OpenAI-compatible" if isinstance(model, OpenAIModel) else "unknown"
        model_id = session_model_id(agent) or "provider default"
        return f"Provider: {provider}\nModel ID: {model_id}"
    return None
