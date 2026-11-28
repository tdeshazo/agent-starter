"""Render conversation events in the terminal transcript."""
from collections.abc import Callable
from dataclasses import dataclass, field

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


def _reasoning_rows(rows: list[str], color: bool) -> list[str]:
    gutter = "  " + sgr("│", DIM, color)
    # The plain StreamCell uses a two-column prefix on each text row.
    return [f"{gutter} {row[2:]}" if row else gutter for row in rows]


def _reasoning_stream(width: int, color: bool) -> StreamCell:
    return StreamCell(width - 2, " ", ITALIC_DIM, color)


@dataclass(eq=False)
class ReasoningBlock:
    """A prompt's reasoning rows, including the section that is still streaming."""

    color: bool
    rows: list[str] = field(default_factory=list)
    stream: StreamCell | None = None
    expanded: bool = False

    def label(self, focused: bool = False) -> str:
        focus = "› " if focused else "  "
        arrow = "▾" if self.expanded else "▸"
        return focus + sgr(f"{arrow} Reasoning", DIM, self.color)

    def details(self) -> list[str]:
        return self.rows + _reasoning_rows(self.stream.tail(), self.color) if self.stream else self.rows

    def push(self, chunk: str, width: int) -> None:
        if self.stream is None:
            self.stream = _reasoning_stream(width, self.color)
        self.rows.extend(_reasoning_rows(self.stream.push(chunk), self.color))

    def finish(self) -> None:
        if self.stream is not None:
            self.rows.extend(_reasoning_rows(self.stream.finish(), self.color))
            self.stream = None


class Transcript:
    """Turn agent events into history cells.

    Finished rows go to ``emit``; ``tail`` returns rows still in progress.
    """

    def __init__(
        self,
        emit: Callable[[list[str]], None],
        width: Callable[[], int],
        color: bool = True,
        *,
        disclose_reasoning: Callable[[ReasoningBlock], None] | None = None,
    ):
        self.emit = emit
        self.width = width
        self.color = color
        self.disclose_reasoning = disclose_reasoning
        self.light = light_background()
        self.true_color = use_true_color()
        self.stream: StreamCell | None = None
        self.stream_kind = ""
        self._stream_opened = False
        self._reasoning: ReasoningBlock | None = None
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
        if not chunk:
            return
        if self.stream is None or self.stream_kind != kind:
            self.close_stream()
            if kind == "reasoning":
                self.stream = _reasoning_stream(self.width(), self.color)
                self.emit(["", sgr("  Reasoning", DIM, self.color)])
            else:
                self.stream = StreamCell(
                    self.width(), "•", color=self.color, markdown=True, light=self.light,
                )
            self.stream_kind = kind
            self._stream_opened = kind == "reasoning"
        self._emit_stream_rows(self.stream.push(chunk))

    def _emit_stream_rows(self, rows: list[str]) -> None:
        if not rows:
            return
        if self.stream_kind == "reasoning":
            rows = _reasoning_rows(rows, self.color)
        if not self._stream_opened:
            rows = [""] + rows
            self._stream_opened = True
        self.emit(rows)

    def close_stream(self) -> None:
        if self._reasoning is not None:
            self._reasoning.finish()
        if self.stream is not None:
            self._emit_stream_rows(self.stream.finish())
            self.stream = None

    def __call__(self, event: ConversationEvent) -> None:
        if isinstance(event, TextDelta):
            if event.reasoning and self.disclose_reasoning is not None:
                if not event.text:
                    return
                if self._reasoning is None:
                    self._reasoning = ReasoningBlock(self.color)
                    self.disclose_reasoning(self._reasoning)
                self._reasoning.push(event.text, self.width())
            else:
                if self._reasoning is not None:
                    self._reasoning.finish()
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
            if self.stream_kind == "reasoning":
                live_rows = _reasoning_rows(live_rows, self.color)
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
        self._reasoning = None
        self.pending_tools.clear()
        if stopped:
            self.error(INTERRUPTED)
        elif self.tool_calls:
            self.cell(separator_cell(elapsed, self.width(), self.color))
        if self._turn_usage:
            self.cell(usage_cell(self._turn_usage, self.width(), self.color))
            self._turn_usage.clear()
        self.tool_calls = 0
