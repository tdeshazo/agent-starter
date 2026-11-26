"""Run the full-screen transcript, composer, and interactive turn lifecycle."""
import asyncio
from pathlib import Path
import re
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

from .commands import COMMANDS, command_output, parse_pet_command
from .pets import PET_NAMES, PETS, load_pet, normalize_pet, pet_rows, pet_width, save_pet
from .rendering import BOLD, BOLD_CYAN, DIM, format_elapsed, format_tokens, header_cell, sgr, shimmer
from .session import conversation_turn, session_info, total_tokens
from .terminal import use_color, use_true_color
from .transcript import Transcript


PLACEHOLDER = "Ask the agent anything"
ESCAPE_TIMEOUT = 0.1
FRAME_INTERVAL = 0.08


def matching_commands(text: str) -> list[str]:
    if not text.startswith("/"):
        return []
    if text.startswith("/pet "):
        arg = re.sub(r"[\s_]+", "-", text[5:].strip().lower())
        return [f"/pet {name}" for name in PET_NAMES if name.startswith(arg)]
    if any(char.isspace() for char in text):
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
        config_path: Path | None = None,
    ):
        self.agent_factory = agent_factory
        self.color = use_color() if color is None else color
        self.config_path = config_path
        self.pet = load_pet(self.config_path)
        self._header_len = 0
        self._pet_picker_index: int | None = None
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

    # Pet selection

    def _open_pet_picker(self) -> None:
        self._pet_picker_index = PET_NAMES.index(self.pet)
        self.app.layout.focus(self._picker_window)
        self.app.invalidate()

    def _close_pet_picker(self) -> None:
        self._pet_picker_index = None
        self.app.layout.focus(self._composer)
        self.app.invalidate()

    def _move_pet_picker(self, delta: int) -> None:
        if self._pet_picker_index is None:
            return
        self._pet_picker_index = (self._pet_picker_index + delta) % len(PET_NAMES)
        self.app.invalidate()

    def _select_pet(self, name: str) -> None:
        canonical = normalize_pet(name)
        if canonical is None:
            choices = ", ".join(PET_NAMES)
            self.transcript.error(f"Unknown pet {name!r}. Choose from: {choices}.")
            return
        try:
            save_pet(canonical, self.config_path)
        except OSError as error:
            self.transcript.error(f"Could not save pet preference: {error}")
            return
        self.pet = canonical
        self._refresh_header()
        self.transcript.info(f"Selected pet: {canonical}.")

    def _refresh_header(self) -> None:
        if self._header_len <= 0 or len(self._history.rows) < self._header_len:
            return
        rows = header_cell(
            width=self._width(),
            color=self.color,
            true_color=use_true_color(),
            pet=self.pet,
            **session_info(self.agent),
        )
        self._history.rows[: self._header_len] = rows
        self._header_len = len(rows)
        self.app.invalidate()

    # Layout

    def _layout(self) -> Layout:
        def ansi(lines: list[str]):
            return ANSI("\n".join(lines))

        def line_prefix(line_number: int, wrap_count: int):
            if line_number == 0 and wrap_count == 0:
                return [("class:prompt", "› ")]
            return [("", "  ")]

        in_picker = Condition(lambda: self._pet_picker_index is not None)
        not_in_picker = Condition(lambda: self._pet_picker_index is None)
        has_commands = Condition(
            lambda: self._pet_picker_index is None and bool(matching_commands(self.buffer.text))
        )
        is_empty = Condition(lambda: not self.buffer.text)

        self._composer = Window(
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
        self._picker_window = Window(
            FormattedTextControl(lambda: ansi(self._pet_picker_rows()), focusable=True),
            dont_extend_height=True,
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
                ConditionalContainer(self._composer, not_in_picker),
                ConditionalContainer(
                    Window(FormattedTextControl(lambda: ansi(self._command_rows())), dont_extend_height=True),
                    has_commands,
                ),
                ConditionalContainer(self._picker_window, in_picker),
                Window(height=Dimension(preferred=1, max=1)),
                footer,
            ]),
            focused_element=self._composer,
        )

    def _status_line(self) -> str:
        elapsed = format_elapsed(time.monotonic() - self.turn_started)
        return (
            "• "
            + shimmer("Working", time.monotonic(), self.color)
            + sgr(f" ({elapsed} • esc to interrupt)", DIM, self.color)
        )

    def _command_description(self, command: str) -> str:
        if command in COMMANDS:
            return COMMANDS[command]
        if command.startswith("/pet "):
            name = command.removeprefix("/pet ")
            pet = PETS.get(name)
            if pet is not None:
                suffix = " (current)" if name == self.pet else ""
                return pet.description + suffix
        return ""

    def _command_rows(self) -> list[str]:
        matches = matching_commands(self.buffer.text)
        if not matches:
            return []
        label_width = max(10, max(len(command) for command in matches) + 2)
        rows = []
        for index, command in enumerate(matches):
            label = command.ljust(label_width)
            description = self._command_description(command)
            if index == 0:
                rows.append("  " + sgr(label, BOLD_CYAN, self.color) + description)
            else:
                rows.append("  " + label + sgr(description, DIM, self.color))
        return rows

    def _pet_picker_rows(self) -> list[str]:
        if self._pet_picker_index is None:
            return []
        selected_name = PET_NAMES[self._pet_picker_index]
        left: list[tuple[str, str]] = [
            ("  Choose a pet", "  " + sgr("Choose a pet", BOLD, self.color)),
            ("", ""),
        ]
        for index, name in enumerate(PET_NAMES):
            pet = PETS[name]
            marker = "› " if index == self._pet_picker_index else "  "
            badge = " (current)" if name == self.pet else ""
            plain = f"  {marker}{pet.label}{badge}"
            if index == self._pet_picker_index:
                styled = "  " + sgr(marker + pet.label, BOLD_CYAN, self.color) + sgr(badge, DIM, self.color)
            else:
                styled = "  " + marker + pet.label + sgr(badge, DIM, self.color)
            left.append((plain, styled))
        description = PETS[selected_name].description
        desc_line = "  " + sgr(description, DIM, self.color)

        art = pet_rows(selected_name, self.color, true_color=use_true_color())
        col_width = max(len(plain) for plain, _ in left) + 4
        if self._width() < col_width + pet_width(selected_name):
            return [styled for _, styled in left] + ["", desc_line]
        height = max(len(left), len(art))
        left += [("", "")] * (height - len(left))
        top_pad = (height - len(art)) // 2
        art = [""] * top_pad + art + [""] * (height - len(art) - top_pad)
        rows = [
            (styled + " " * (col_width - len(plain)) + art_line).rstrip()
            for (plain, styled), art_line in zip(left, art)
        ]
        rows.extend(["", desc_line])
        return rows

    def _footer_hints(self) -> str:
        if self._pet_picker_index is not None:
            hints = ["↑/↓ choose", "⏎ select", "esc cancel"]
        elif self.running:
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
        in_picker = Condition(lambda: self._pet_picker_index is not None)
        not_in_picker = Condition(lambda: self._pet_picker_index is None)

        @bindings.add("pageup")
        def page_up(event):
            self._scroll_history(-1)

        @bindings.add("pagedown")
        def page_down(event):
            self._scroll_history(1)

        @bindings.add("up", filter=in_picker)
        @bindings.add("left", filter=in_picker)
        @bindings.add("k", filter=in_picker)
        def picker_prev(event):
            self._move_pet_picker(-1)

        @bindings.add("down", filter=in_picker)
        @bindings.add("right", filter=in_picker)
        @bindings.add("j", filter=in_picker)
        @bindings.add("tab", filter=in_picker)
        def picker_next(event):
            self._move_pet_picker(1)

        @bindings.add("enter", filter=in_picker)
        def picker_select(event):
            index = self._pet_picker_index
            self._close_pet_picker()
            if index is not None:
                self._select_pet(PET_NAMES[index])

        @bindings.add("escape", eager=True, filter=in_picker)
        def picker_cancel(event):
            self._close_pet_picker()

        @bindings.add("enter", filter=not_in_picker)
        def submit(event):
            self.submit()

        @bindings.add("escape", "enter", filter=not_in_picker)
        @bindings.add("c-j", filter=not_in_picker)
        def newline(event):
            self.buffer.insert_text("\n")

        @bindings.add("tab", filter=not_in_picker)
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
            if self._pet_picker_index is not None:
                self._close_pet_picker()
            elif self.running:
                self.interrupt()
            elif self.buffer.text:
                self.buffer.reset()
            else:
                self.app.exit()

        @bindings.add("c-d", filter=not_in_picker)
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
        is_pet, pet_arg = parse_pet_command(prompt)
        if prompt == "/exit":
            self.app.exit()
        elif prompt == "/clear":
            self._set_agent(self.agent_factory())
            self.transcript.info("Started a new conversation.")
        elif is_pet:
            if pet_arg is None:
                self._open_pet_picker()
            else:
                self._select_pet(pet_arg)
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
        start = len(self._history.rows)
        self.transcript.header(pet=self.pet, **session_info(self.agent))
        self._header_len = len(self._history.rows) - start

    async def run_async(self) -> None:
        await self.app.run_async(pre_run=self._header)

    def run(self) -> None:
        asyncio.run(self.run_async())
