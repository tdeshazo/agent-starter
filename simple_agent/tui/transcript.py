"""Render conversation events in the terminal transcript."""
from collections.abc import Callable

from ..conversation import ConversationEvent, TextDelta, TokenUsage, ToolCall, ToolResult
from .rendering import (
    DIM,
    ITALIC_DIM,
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
from .terminal import light_background, use_true_color


INTERRUPTED = "Response stopped — tell the agent what to do differently."


class Transcript:
    """Turn agent events into history cells.

    Finished rows go to ``emit``; ``tail`` returns rows still in progress.
    """

    def __init__(self, emit: Callable[[list[str]], None], width: Callable[[], int], color: bool = True):
        self.emit = emit
        self.width = width
        self.color = color
        self.light = light_background()
        self.true_color = use_true_color()
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

    def header_rows(self, width: int, **kwargs) -> list[str]:
        return header_cell(width=width, color=self.color, true_color=self.true_color, **kwargs)

    def header(self, **kwargs) -> None:
        self.emit(self.header_rows(self.width(), **kwargs))

    def user(self, text: str) -> None:
        self.cell(user_cell(text, self.width(), self.color, light=self.light))

    def info(self, message: str) -> None:
        self.cell(info_cell(message, self.width(), self.color))

    def error(self, message: str) -> None:
        self.cell(error_cell(message, self.width(), self.color))

    def _write(self, kind: str, chunk: str) -> None:
        if self.stream is None or self.stream_kind != kind:
            self.close_stream()
            if kind == "reasoning":
                self.stream = StreamCell(self.width(), sgr("•", DIM, self.color), ITALIC_DIM, self.color)
            else:
                self.stream = StreamCell(
                    self.width(), "•", color=self.color, markdown=True, light=self.light,
                )
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

    def __call__(self, event: ConversationEvent) -> None:
        if isinstance(event, TextDelta):
            self._write("reasoning" if event.reasoning else "text", event.text)
        elif isinstance(event, TokenUsage):
            for key, count in event.counts.items():
                self._turn_usage[key] = self._turn_usage.get(key, 0) + count
        elif isinstance(event, ToolCall):
            self.close_stream()
            self.pending_tools[event.id] = (event.name, event.arguments)
        elif isinstance(event, ToolResult):
            name, arguments = self.pending_tools.pop(event.id, ("tool", None))
            self.tool_calls += 1
            width = self.width()
            self.cell(
                tool_call_rows(name, arguments, width, self.color)
                + tool_result_rows(event, width, self.color)
            )

    def tail(self, *, separate_stream: bool = False) -> list[str]:
        """Rows for the live pane: the partial streamed row and running tools."""
        rows = []
        if self.stream is not None:
            live_rows = self.stream.tail()
            if separate_stream and live_rows and not self._stream_opened:
                rows.append("")
            rows.extend(live_rows)
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
