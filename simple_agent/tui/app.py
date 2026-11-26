"""Run the full-screen transcript, composer, and interactive turn lifecycle."""
import asyncio
import time
from collections.abc import Callable
from functools import cache

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.data_structures import Point
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import ANSI, fragment_list_to_text, to_formatted_text
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.input import Input
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.key_binding.defaults import load_key_bindings
from prompt_toolkit.layout import (
    ConditionalContainer,
    FormattedTextControl,
    HSplit,
    Layout,
    VSplit,
    Window,
    WindowAlign,
)
from prompt_toolkit.layout.controls import BufferControl, UIContent, UIControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.processors import AfterInput, ConditionalProcessor
from prompt_toolkit.output import Output
from prompt_toolkit.styles import Style

from .commands import COMMANDS, command_output
from .rendering import BOLD_CYAN, DIM, format_elapsed, format_tokens, sgr, shimmer
from .session import conversation_turn, session_info, total_tokens
from .terminal import use_color
from .transcript import Transcript


PLACEHOLDER = "Ask the agent anything"
ESCAPE_TIMEOUT = 0.1
FRAME_INTERVAL = 0.08


def matching_commands(text: str) -> list[str]:
    if not text.startswith("/") or any(char.isspace() for char in text):
        return []
    return [command for command in COMMANDS if command.startswith(text)]


class TranscriptControl(UIControl):
    """Provide the transcript to prompt-toolkit, formatting rows as it reads them."""

    def __init__(self, tail: Callable[[], list[str]]):
        self.rows: list[str] = []
        self.tail = tail
        self.first_line: int | None = None

    def create_content(self, width: int, height: int | None) -> UIContent:
        committed = len(self.rows)
        tail = self.tail()
        count = committed + len(tail)
        if not count:
            return UIContent(line_count=1, show_cursor=False)

        @cache
        def get_line(index: int):
            line = self.rows[index] if index < committed else tail[index - committed]
            return to_formatted_text(ANSI(line))

        if self.first_line is None:
            row = count - 1
            column = len(fragment_list_to_text(get_line(row)))
        else:
            row = min(self.first_line, count - 1)
            column = 0
        return UIContent(get_line, count, cursor_position=Point(column, row), show_cursor=False)


class AgentTui:
    """Full-screen terminal UI with a scrollable transcript above the composer."""

    def __init__(
        self,
        agent_factory: Callable[[], object],
        agent=None,
        *,
        input: Input | None = None,
        output: Output | None = None,
        color: bool | None = None,
    ):
        self.agent_factory = agent_factory
        self.color = use_color() if color is None else color
        self.transcript = Transcript(self._emit, self._width, self.color)
        self._history = TranscriptControl(self.transcript.tail)
        self._history_window = Window(self._history, height=Dimension(min=1), wrap_lines=True)
        self.agent = None
        self._set_agent(agent if agent is not None else agent_factory())
        self.task: asyncio.Task | None = None
        self.turn_started = 0.0
        self.stop_requested = False
        self.buffer = Buffer(multiline=True, history=InMemoryHistory())
        self.app = Application(
            layout=self._layout(),
            key_bindings=merge_key_bindings([load_key_bindings(), self._bindings()]),
            style=Style.from_dict(
                {"prompt": "bold ansicyan", "placeholder": "ansibrightblack italic"} if self.color else {}
            ),
            full_screen=True,
            erase_when_done=True,
            input=input,
            output=output,
        )
        self.app.ttimeoutlen = ESCAPE_TIMEOUT

    # Agent and output plumbing

    def _set_agent(self, agent) -> None:
        self.agent = agent
        agent.callback_handler = self.transcript

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    def _width(self) -> int:
        return self.app.output.get_size().columns

    def _emit(self, lines: list[str]) -> None:
        self._history.rows.extend(lines)
        self.app.invalidate()

    # Layout

    def _layout(self) -> Layout:
        def ansi(lines: list[str]):
            return ANSI("\n".join(lines))

        def line_prefix(line_number: int, wrap_count: int):
            if line_number == 0 and wrap_count == 0:
                return [("class:prompt", "› ")]
            return [("", "  ")]

        has_commands = Condition(lambda: bool(matching_commands(self.buffer.text)))
        is_empty = Condition(lambda: not self.buffer.text)

        composer = Window(
            BufferControl(
                self.buffer,
                input_processors=[
                    ConditionalProcessor(AfterInput(PLACEHOLDER, style="class:placeholder"), is_empty)
                ],
            ),
            get_line_prefix=line_prefix,
            wrap_lines=True,
            dont_extend_height=True,
            height=Dimension(min=1, max=12),
        )
        footer = VSplit([
            Window(FormattedTextControl(lambda: ansi([self._footer_hints()])), height=1),
            Window(
                FormattedTextControl(lambda: ansi([self._footer_status()])),
                height=1,
                align=WindowAlign.RIGHT,
            ),
        ])
        return Layout(
            HSplit([
                self._history_window,
                ConditionalContainer(
                    Window(FormattedTextControl(lambda: ansi([self._status_line()])), height=1),
                    Condition(lambda: self.running),
                ),
                Window(height=Dimension(preferred=1, max=1)),
                composer,
                ConditionalContainer(
                    Window(FormattedTextControl(lambda: ansi(self._command_rows())), dont_extend_height=True),
                    has_commands,
                ),
                Window(height=Dimension(preferred=1, max=1)),
                footer,
            ]),
            focused_element=composer,
        )

    def _status_line(self) -> str:
        elapsed = format_elapsed(time.monotonic() - self.turn_started)
        return (
            "• "
            + shimmer("Working", time.monotonic(), self.color)
            + sgr(f" ({elapsed} • esc to interrupt)", DIM, self.color)
        )

    def _command_rows(self) -> list[str]:
        matches = matching_commands(self.buffer.text)
        rows = []
        for index, command in enumerate(matches):
            label = command.ljust(10)
            if index == 0:
                rows.append("  " + sgr(label, BOLD_CYAN, self.color) + COMMANDS[command])
            else:
                rows.append("  " + label + sgr(COMMANDS[command], DIM, self.color))
        return rows

    def _footer_hints(self) -> str:
        if self.running:
            hints = ["esc interrupt", "⌃C interrupt"]
        elif matching_commands(self.buffer.text):
            hints = ["tab complete", "⏎ run"]
        elif self.buffer.text:
            hints = ["⏎ send", "⌥⏎ newline", "⌃C clear"]
        else:
            hints = ["⏎ send", "⌥⏎ newline", "/ commands", "PgUp/PgDn scroll", "⌃C quit"]
        return "  " + sgr("   ".join(hints), DIM, self.color)

    def _footer_status(self) -> str:
        tokens = total_tokens(self.agent)
        return sgr(f"{format_tokens(tokens)} tokens used  ", DIM, self.color) if tokens else ""

    # Input handling

    def _scroll_history(self, direction: int) -> None:
        info = self._history_window.render_info
        if info is None or not info.displayed_lines:
            return
        first = info.first_visible_line()
        last = info.last_visible_line()
        if direction < 0 and first == 0:
            return
        page = max(1, last - first)
        if direction > 0 and last + page >= info.content_height - 1:
            self._history.first_line = None
        else:
            self._history.first_line = max(0, first + direction * page)
            self._history_window.vertical_scroll = self._history.first_line

    def _bindings(self) -> KeyBindings:
        bindings = KeyBindings()

        @bindings.add("pageup")
        def page_up(event):
            self._scroll_history(-1)

        @bindings.add("pagedown")
        def page_down(event):
            self._scroll_history(1)

        @bindings.add("enter")
        def submit(event):
            self.submit()

        @bindings.add("escape", "enter")
        @bindings.add("c-j")
        def newline(event):
            self.buffer.insert_text("\n")

        @bindings.add("tab")
        def complete(event):
            matches = matching_commands(self.buffer.text)
            if matches:
                self.buffer.text = matches[0]
                self.buffer.cursor_position = len(self.buffer.text)

        # Eager so Esc interrupts at once instead of waiting to see whether it
        # starts a key sequence; only while running, so Alt+Enter works when idle.
        @bindings.add("escape", eager=True, filter=Condition(lambda: self.running))
        def escape(event):
            self.interrupt()

        @bindings.add("c-c")
        def control_c(event):
            if self.running:
                self.interrupt()
            elif self.buffer.text:
                self.buffer.reset()
            else:
                self.app.exit()

        @bindings.add("c-d")
        def control_d(event):
            if not self.buffer.text and not self.running:
                self.app.exit()
            else:
                self.buffer.delete()

        return bindings

    def submit(self) -> None:
        if self.running:
            return
        entered = self.buffer.text
        prompt = entered.strip()
        if not prompt:
            return
        matches = matching_commands(prompt)
        if prompt.startswith("/") and prompt not in COMMANDS and len(matches) == 1:
            prompt = matches[0]
        self.buffer.append_to_history()
        self.buffer.reset()
        self._history.first_line = None
        if prompt == "/exit":
            self.app.exit()
        elif prompt == "/clear":
            self._set_agent(self.agent_factory())
            self.transcript.info("Started a new conversation.")
        elif result := command_output(prompt, self.agent):
            self.transcript.info(result)
        elif prompt.startswith("/") and not any(char.isspace() for char in prompt):
            self.transcript.error(f"Unknown command {prompt}. Type / to see available commands.")
        else:
            self.transcript.user(entered)
            self.turn_started = time.monotonic()
            self.stop_requested = False
            self.task = self.app.create_background_task(self._respond(prompt))
            self.app.create_background_task(self._animate())

    def interrupt(self) -> None:
        if self.running:
            self.stop_requested = True
            self.task.cancel()

    async def _respond(self, prompt: str) -> None:
        agent = self.agent
        stopped = False
        try:
            with conversation_turn(agent.messages):
                await agent.invoke_async(prompt)
        except asyncio.CancelledError:
            if not self.stop_requested:
                raise
            stopped = True
        except Exception as error:
            self.transcript.invocation_failed(error)
        finally:
            self.transcript.end_turn(time.monotonic() - self.turn_started, stopped)
            self.app.invalidate()

    async def _animate(self) -> None:
        while self.running:
            self.app.invalidate()
            await asyncio.sleep(FRAME_INTERVAL)

    # Entry points

    def _header(self) -> None:
        self.transcript.header(**session_info(self.agent))

    async def run_async(self) -> None:
        await self.app.run_async(pre_run=self._header)

    def run(self) -> None:
        asyncio.run(self.run_async())
