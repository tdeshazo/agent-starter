"""Manage conversation lifecycle independently of the model SDK and interface."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol

from .preferences import AgentPreferences, UserPreferences


@dataclass(frozen=True)
class SessionDetails:
    name: str
    system_prompt: str
    provider: str
    model: str | None
    endpoint: str | None


@dataclass(frozen=True)
class ToolSpec:
    name: str
    summary: str


@dataclass(frozen=True)
class TextDelta:
    text: str
    reasoning: bool = False


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: object


@dataclass(frozen=True)
class ToolResult:
    id: str
    parts: tuple[str, ...]
    failed: bool


@dataclass(frozen=True)
class TokenUsage:
    counts: dict[str, int]


type ConversationEvent = TextDelta | ToolCall | ToolResult | TokenUsage


class InvocationError(Exception):
    """A safe description of a failed model operation."""


class ConversationBackend(Protocol):
    def apply(self, preferences: AgentPreferences) -> None: ...
    def observe(self, emit: Callable[[ConversationEvent], None]) -> None: ...
    def details(self) -> SessionDetails: ...
    def tools(self) -> list[ToolSpec]: ...
    def total_tokens(self) -> int: ...
    def checkpoint(self) -> object: ...
    def restore(self, checkpoint: object) -> None: ...
    def invoke(self, prompt: str) -> None: ...
    async def invoke_async(self, prompt: str) -> None: ...


class Conversation:
    def __init__(
        self,
        backend_factory: Callable[[], ConversationBackend],
        preferences: UserPreferences,
        *,
        initial_backend: ConversationBackend | None = None,
    ):
        self._backend_factory = backend_factory
        self._preferences = preferences
        self._observer: Callable[[ConversationEvent], None] | None = None
        backend = initial_backend if initial_backend is not None else backend_factory()
        self._backend = self._prepare(backend)

    def _prepare(self, backend: ConversationBackend) -> ConversationBackend:
        backend.apply(self._preferences.agent())
        if self._observer is not None:
            backend.observe(self._observer)
        return backend

    def observe(self, emit: Callable[[ConversationEvent], None]) -> None:
        self._backend.observe(emit)
        self._observer = emit

    def reset(self) -> None:
        self._backend = self._prepare(self._backend_factory())

    def update_preferences(self, name: str, prompt: str) -> None:
        self._backend.apply(self._preferences.save_agent(name, prompt))

    def details(self) -> SessionDetails:
        return self._backend.details()

    def tools(self) -> list[ToolSpec]:
        return self._backend.tools()

    def total_tokens(self) -> int:
        return self._backend.total_tokens()

    @contextmanager
    def _turn(self) -> Iterator[ConversationBackend]:
        backend = self._backend
        previous = backend.checkpoint()
        try:
            yield backend
        except BaseException:
            backend.restore(previous)
            raise

    def invoke(self, prompt: str) -> None:
        with self._turn() as backend:
            backend.invoke(prompt)

    async def invoke_async(self, prompt: str) -> None:
        with self._turn() as backend:
            await backend.invoke_async(prompt)
