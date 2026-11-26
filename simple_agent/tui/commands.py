"""Describe slash commands and format local session information."""
from dataclasses import dataclass
import re

from strands.models.openai import OpenAIModel

from .pets import PET_NAMES
from .session import session_model_id


COMMANDS = {
    "/clear": "clear the transcript and start a new conversation",
    "/exit": "exit the agent",
    "/pet": f"choose a companion pet ({len(PET_NAMES)} available)",
    "/settings": "edit the agent name and system prompt",
    "/tools": "list the registered tools",
    "/status": "show the active provider and model ID",
}


@dataclass(frozen=True)
class SlashCommand:
    name: str
    arg: str | None = None
    error: str | None = None


def matching_commands(text: str) -> list[str]:
    if not text.startswith("/"):
        return []
    if text.startswith("/pet "):
        arg = re.sub(r"[\s_]+", "-", text[5:].strip().lower())
        return [f"/pet {name}" for name in PET_NAMES if name.startswith(arg)]
    if any(char.isspace() for char in text):
        return []
    return [command for command in COMMANDS if command.startswith(text)]


def parse_pet_command(prompt: str) -> tuple[bool, str | None]:
    """Parse ``/pet`` or ``/pet <name>`` into ``(is_pet_command, arg)``."""
    parts = prompt.split(None, 1)
    if not parts or parts[0] != "/pet":
        return False, None
    return True, parts[1].strip() if len(parts) > 1 else None


def parse_slash_command(prompt: str, *, interactive: bool = True) -> SlashCommand | None:
    """Resolve a user input line into a slash command, or ``None`` for agent prompts."""
    if not prompt.startswith("/"):
        return None
    matches = matching_commands(prompt)
    if prompt not in COMMANDS and len(matches) == 1:
        prompt = matches[0]
    is_pet, pet_arg = parse_pet_command(prompt)
    if is_pet:
        return SlashCommand("/pet", arg=pet_arg)
    head, *rest = prompt.split(None, 1)
    if head in COMMANDS:
        if rest:
            return SlashCommand(head, error=f"Command {head} does not take arguments.")
        return SlashCommand(head)
    if not rest:
        hint = (
            "Type / to see available commands."
            if interactive
            else f"Available commands: {', '.join(COMMANDS)}."
        )
        return SlashCommand(head, error=f"Unknown command {prompt}. {hint}")
    return None


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
