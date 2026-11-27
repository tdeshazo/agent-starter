"""Interpret and validate user preferences independently of their storage."""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass


DEFAULT_AGENT_NAME = "Simple Agent"
PET_NAMES = (
    "frog",
    "rabbit",
    "cat",
    "octopus",
    "alien",
    "robot",
    "moth",
    "axolotl",
    "hermit-crab",
    "ghost",
    "snail",
    "mimic",
    "crt",
    "ooze",
    "orb",
)
DEFAULT_PET = "frog"


def pet_slug(name: str) -> str:
    return re.sub(r"[\s_]+", "-", name.strip().lower())


def normalize_pet(name: object) -> str | None:
    if isinstance(name, str) and (slug := pet_slug(name)) in PET_NAMES:
        return slug
    return None


def normalize_agent_name(value: object) -> str | None:
    """Accept a nonempty, single-line name suitable for display in the terminal."""
    if not isinstance(value, str):
        return None
    name = value.strip()
    if not name or any(unicodedata.category(char) in {"Cc", "Cs", "Zl", "Zp"} for char in name):
        return None
    return name


@dataclass(frozen=True)
class AgentPreferences:
    name: str | None
    system_prompt: str | None

    @classmethod
    def from_settings(cls, data: dict) -> AgentPreferences:
        prompt = data.get("system_prompt")
        return cls(
            normalize_agent_name(data.get("agent_name")),
            prompt if isinstance(prompt, str) else None,
        )

    def overrides(self) -> dict[str, str]:
        return {
            key: value
            for key, value in (("agent_name", self.name), ("system_prompt", self.system_prompt))
            if value is not None
        }


def apply_preferences(agent, preferences: AgentPreferences) -> None:
    if preferences.name is not None:
        agent.name = preferences.name
    if preferences.system_prompt is not None:
        agent.system_prompt = preferences.system_prompt or None


class UserPreferences:
    """Read and update preferences through an injected store."""

    def __init__(self, load: Callable[[], dict], save: Callable[[dict], None]):
        self._load = load
        self._save = save

    def agent(self) -> AgentPreferences:
        return AgentPreferences.from_settings(self._load())

    def save_agent(self, name: str, prompt: str) -> AgentPreferences:
        normalized = normalize_agent_name(name)
        if normalized is None:
            raise ValueError("Enter a name on one line.")
        if not isinstance(prompt, str):
            raise ValueError("Enter the system prompt as text.")
        preferences = AgentPreferences(normalized, prompt)
        self._save(preferences.overrides())
        return preferences

    def pet(self) -> str:
        return normalize_pet(self._load().get("pet")) or DEFAULT_PET

    def select_pet(self, name: str) -> str:
        canonical = normalize_pet(name)
        if canonical is None:
            choices = ", ".join(PET_NAMES)
            raise ValueError(f"Unknown pet {name!r}. Choose from: {choices}.")
        self._save({"pet": canonical})
        return canonical

    def scroll_speed(self) -> float:
        value = self._load().get("mouse_scroll_speed")
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            if isinstance(value, int) or math.isfinite(value):
                return float(min(value, 20))
        return 1.0
