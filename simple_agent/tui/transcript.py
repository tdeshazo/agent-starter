"""Adapt Strands callback events to the terminal transcript."""
from collections.abc import Callable

from .rendering import (
    DIM,
    ITALIC_DIM,
    TOKEN_USAGE_FIELDS,
    StreamCell,
    error_cell,
    header_cell,
    info_cell,
    separator_cell,
    sgr,
    tool_call_rows,
    tool_result_rows,
    usage_cell,
    user_cell,
)
from .terminal import use_true_color


INTERRUPTED = "Response stopped — tell the agent what to do differently."


def format_invocation_error(error: Exception) -> str:
    """Format a safe, user-facing description of a provider or runtime failure."""
    status = getattr(error, "status_code", None)
    cause = getattr(error, "__cause__", None)
    name = type(error).__name__
    if isinstance(error, TimeoutError) or name == "APITimeoutError":
        message = "Provider timed out"
    elif isinstance(status, int):
        message = f"Provider request failed (HTTP {status})"
    elif isinstance(error, ConnectionError) or isinstance(cause, ConnectionError) or name == "APIConnectionError":
        message = "Could not connect to model server"
    else:
        message = "The response failed. Try again."
    return f"{name}: {message}"


class Transcript:
    """Turn agent events into history cells.

    Finished rows go to ``emit``; ``tail`` returns rows still in progress.
    """

    def __init__(self, emit: Callable[[list[str]], None], width: Callable[[], int], color: bool = True):
        self.emit = emit
        self.width = width
        self.color = color
        self.stream: StreamCell | None = None
        self.stream_kind = ""
        self._stream_opened = False
        self.pending_tools: dict[str, tuple[str, object]] = {}
        self.tool_calls = 0
        self._turn_usage: dict[str, int] = {}

    def cell(self, lines: list[str]) -> None:
        """Emit a new history cell, separated from the previous one by a blank line."""
        self.close_stream()
        self.emit([""] + lines)

    def header(self, **kwargs) -> None:
        self.emit(header_cell(
            width=self.width(), color=self.color, true_color=use_true_color(), **kwargs,
        ))

    def user(self, text: str) -> None:
        self.cell(user_cell(text, self.width(), self.color))

    def info(self, message: str) -> None:
        self.cell(info_cell(message, self.width(), self.color))

    def error(self, message: str) -> None:
        self.cell(error_cell(message, self.width(), self.color))

    def invocation_failed(self, error: Exception) -> None:
        """Show a safe description while preserving the terminal session."""
        self.error(format_invocation_error(error))

    def _write(self, kind: str, chunk: str) -> None:
        if self.stream is None or self.stream_kind != kind:
            self.close_stream()
            if kind == "reasoning":
                self.stream = StreamCell(self.width(), sgr("•", DIM, self.color), ITALIC_DIM, self.color)
            else:
                self.stream = StreamCell(self.width(), "•", "", self.color, markdown=True)
            self.stream_kind = kind
            self._stream_opened = False
        rows = self.stream.push(chunk)
        if rows:
            if not self._stream_opened:
                rows = [""] + rows
                self._stream_opened = True
            self.emit(rows)

    def close_stream(self) -> None:
        if self.stream is not None:
            rows = self.stream.finish()
            if rows and not self._stream_opened:
                rows = [""] + rows
            self.stream = None
            if rows:
                self.emit(rows)

    def __call__(self, **event) -> None:
        """Strands callback handler."""
        if chunk := event.get("reasoningText"):
            self._write("reasoning", chunk)
        if chunk := event.get("data"):
            self._write("text", chunk)
        message = event.get("message")
        if isinstance(message, dict):
            self._message(message)

    def _message(self, message: dict) -> None:
        usage = (message.get("metadata") or {}).get("usage") or {}
        # Strands supplies zero input and output defaults when usage is missing.
        if usage.get("inputTokens") or usage.get("outputTokens") or usage.get("cacheReadInputTokens") is not None:
            for key, _ in TOKEN_USAGE_FIELDS:
                count = usage.get(key)
                if type(count) is int and count >= 0:
                    self._turn_usage[key] = self._turn_usage.get(key, 0) + count
        for block in message.get("content", []):
            if tool_use := block.get("toolUse"):
                self.close_stream()
                self.pending_tools[tool_use.get("toolUseId", "")] = (tool_use.get("name", "tool"), tool_use.get("input"))
            elif result := block.get("toolResult"):
                name, tool_input = self.pending_tools.pop(result.get("toolUseId", ""), ("tool", None))
                self.tool_calls += 1
                width = self.width()
                self.cell(
                    tool_call_rows(name, tool_input, width, self.color)
                    + tool_result_rows(result, width, self.color)
                )

    def tail(self) -> list[str]:
        """Rows for the live pane: the partial streamed row and running tools."""
        rows = []
        if self.stream is not None:
            rows.extend(self.stream.tail())
        width = self.width()
        for name, tool_input in self.pending_tools.values():
            rows.append("")
            rows.extend(tool_call_rows(name, tool_input, width, self.color, verb="Calling"))
        return rows

    def end_turn(self, elapsed: float, stopped: bool = False) -> None:
        self.close_stream()
        self.pending_tools.clear()
        if stopped:
            self.error(INTERRUPTED)
        elif self.tool_calls:
            self.cell(separator_cell(elapsed, self.width(), self.color))
        if self._turn_usage:
            self.cell(usage_cell(self._turn_usage, self.width(), self.color))
            self._turn_usage.clear()
        self.tool_calls = 0
