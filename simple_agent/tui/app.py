"""Run the full-screen transcript, composer, and interactive turn lifecycle."""
import asyncio
import time
from collections.abc import Callable
from functools import cache

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.data_structures import Point
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import ANSI, fragment_list_to_text, to_formatted_text
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.input import Input
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.key_binding.defaults import load_key_bindings
from prompt_toolkit.keys import Keys
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
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType
from prompt_toolkit.output import Output
from prompt_toolkit.styles import Style

from ..conversation import Conversation, InvocationError
from ..preferences import PET_NAMES, UserPreferences
from .commands import COMMANDS, command_output, matching_commands, parse_slash_command
from .pets import PETS, pet_rows, pet_width
from .rendering import BOLD, BOLD_CYAN, DIM, format_elapsed, format_tokens, sgr, shimmer
from .session import header_context, session_info
from .terminal import use_color
from .transcript import Transcript


PLACEHOLDER = "Ask the agent anything"
ESCAPE_TIMEOUT = 0.1
FRAME_INTERVAL = 0.08
MOUSE_SCROLL_LINES = 3


class _WheelFallbackWindow(Window):
    """Delegate mouse-wheel events unless this window can scroll its own content."""

    def __init__(self, *args, on_wheel: Callable[[int], None], **kwargs):
        super().__init__(*args, **kwargs)
        self._on_wheel = on_wheel

    def _can_scroll_self(self, direction: int) -> bool:
        info = self.render_info
        if info is None or info.content_height <= info.window_height:
            return False
        if direction < 0:
            return self.vertical_scroll > 0
        return info.last_visible_line() < info.content_height - 1

    def _mouse_handler(self, mouse_event: MouseEvent):
        if mouse_event.event_type == MouseEventType.SCROLL_UP:
            if self._can_scroll_self(-1):
                return super()._mouse_handler(mouse_event)
            self._on_wheel(-1)
            return None
        if mouse_event.event_type == MouseEventType.SCROLL_DOWN:
            if self._can_scroll_self(1):
                return super()._mouse_handler(mouse_event)
            self._on_wheel(1)
            return None
        return super()._mouse_handler(mouse_event)


class TranscriptControl(UIControl):
    """Provide the transcript to prompt-toolkit, formatting rows as it reads them."""

    def __init__(
        self,
        tail: Callable[[], list[str]],
        on_width_change: Callable[[int], None] | None = None,
        on_wheel: Callable[[int], None] | None = None,
        focusable: Callable[[], bool] | None = None,
    ):
        self.rows: list[str] = []
        self.tail = tail
        self.on_width_change = on_width_change
        self.on_wheel = on_wheel
        self._focusable = focusable
        self.first_line: int | None = None

    def is_focusable(self) -> bool:
        return self._focusable() if self._focusable is not None else False

    def mouse_handler(self, mouse_event: MouseEvent):
        if self.on_wheel is not None:
            if mouse_event.event_type == MouseEventType.SCROLL_UP:
                self.on_wheel(-1)
                return None
            if mouse_event.event_type == MouseEventType.SCROLL_DOWN:
                self.on_wheel(1)
                return None
        return NotImplemented

    def create_content(self, width: int, height: int | None) -> UIContent:
        if self.on_width_change is not None:
            self.on_width_change(width)
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
        conversation: Conversation,
        preferences: UserPreferences,
        *,
        input: Input | None = None,
        output: Output | None = None,
        color: bool | None = None,
    ):
        self.conversation = conversation
        self._header_context = header_context()
        self.color = use_color() if color is None else color
        self.preferences = preferences
        self.pet = preferences.pet()
        self.mouse_scroll_speed = preferences.scroll_speed()
        self._scroll_remainder = 0.0
        self._header_len = 0
        self._header_width = 0
        self._in_pager = False
        self._pet_picker_index: int | None = None
        self._editing_settings = False
        self._settings_error = ""
        self._name_buffer = Buffer(multiline=False)
        self._system_prompt_buffer = Buffer(multiline=True)
        self.transcript = Transcript(self._emit, self._width, self.color)
        self._history = TranscriptControl(
            lambda: self.transcript.tail(separate_stream=True),
            on_width_change=self._sync_width,
            on_wheel=self._scroll_wheel,
            focusable=lambda: self._in_pager,
        )
        self._history_window = Window(self._history, height=Dimension(min=1), wrap_lines=True)
        self.conversation.observe(self.transcript)
        self.task: asyncio.Task | None = None
        self.turn_started = 0.0
        self.stop_requested = False
        self.buffer = Buffer(multiline=True, history=InMemoryHistory())
        self.app = Application(
            layout=self._layout(),
            key_bindings=merge_key_bindings([load_key_bindings(), self._bindings()]),
            style=Style.from_dict(
                {
                    "user": "#005f5f" if self.transcript.light else "#afd7d7",
                    "prompt": "bold ansicyan",
                    "placeholder": "ansibrightblack italic",
                }
                if self.color
                else {}
            ),
            full_screen=True,
            mouse_support=Condition(lambda: not self._editing_settings),
            erase_when_done=True,
            input=input,
            output=output,
        )
        self.app.ttimeoutlen = ESCAPE_TIMEOUT

    # Agent and output plumbing

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    def _width(self) -> int:
        return self.app.output.get_size().columns

    def _emit(self, lines: list[str]) -> None:
        self._history.rows.extend(lines)
        self.app.invalidate()

    # Transcript overlay (Ctrl+T)

    def _open_pager(self) -> None:
        if self._in_pager:
            return
        self._in_pager = True
        self.app.layout.focus(self._history_window)
        self.app.invalidate()

    def _close_pager(self) -> None:
        if not self._in_pager:
            return
        self._in_pager = False
        self.app.layout.focus(self._composer)
        self.app.invalidate()

    def _toggle_pager(self) -> None:
        if self._in_pager:
            self._close_pager()
        else:
            self._open_pager()

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
        try:
            canonical = self.preferences.select_pet(name)
        except ValueError as error:
            self.transcript.error(str(error))
            return
        except OSError as error:
            self.transcript.error(f"Could not save pet preference: {error}")
            return
        self.pet = canonical
        self._refresh_header()
        self.transcript.info(f"Selected pet: {canonical}.")

    # Agent settings

    def _open_settings(self) -> None:
        details = self.conversation.details()
        name, prompt = details.name, details.system_prompt
        self._name_buffer.reset(Document(name, len(name)))
        self._system_prompt_buffer.reset(Document(prompt))
        self._settings_error = ""
        self._editing_settings = True
        self.app.layout.focus(self._name_field)

    def _close_settings(self) -> None:
        self._editing_settings = False
        self.app.layout.focus(self._composer)

    def _save_agent_settings(self) -> None:
        try:
            self.conversation.update_preferences(self._name_buffer.text, self._system_prompt_buffer.text)
        except ValueError as error:
            self._settings_error = str(error)
            self.app.layout.focus(self._name_field)
            return
        except OSError as error:
            self._settings_error = f"Could not save settings: {error.strerror or error}"
            return
        self._close_settings()
        self._refresh_header()
        self.transcript.info("Agent settings saved.")

    def _refresh_header(self, width: int | None = None, *, invalidate: bool = True) -> None:
        if self._header_len <= 0 or len(self._history.rows) < self._header_len:
            return
        target_width = self._width() if width is None else width
        rows = self.transcript.header_rows(
            target_width, pet=self.pet, **session_info(self.conversation.details(), self._header_context),
        )
        self._history.rows[: self._header_len] = rows
        self._header_len = len(rows)
        self._header_width = target_width
        if invalidate:
            self.app.invalidate()

    def _sync_width(self, width: int) -> None:
        if width != self._header_width and self._header_len > 0:
            self._refresh_header(width=width, invalidate=False)

    # Layout

    def _layout(self) -> Layout:
        def ansi(lines: list[str]):
            return ANSI("\n".join(lines))

        def line_prefix(line_number: int, wrap_count: int):
            if line_number == 0 and wrap_count == 0:
                return [("class:prompt", "› ")]
            return [("", "  ")]

        def wheel_window(*args, **kwargs) -> Window:
            return _WheelFallbackWindow(*args, on_wheel=self._handle_surface_wheel, **kwargs)

        in_pager = Condition(lambda: self._in_pager)
        in_picker = ~in_pager & Condition(lambda: self._pet_picker_index is not None)
        in_settings = ~in_pager & Condition(lambda: self._editing_settings)
        in_composer = ~in_pager & ~in_picker & ~in_settings
        has_commands = in_composer & Condition(lambda: bool(matching_commands(self.buffer.text)))
        is_running = Condition(lambda: self.running)
        is_empty = Condition(lambda: not self.buffer.text)

        self._composer = wheel_window(
            BufferControl(
                self.buffer,
                input_processors=[
                    ConditionalProcessor(AfterInput(PLACEHOLDER, style="class:placeholder"), is_empty)
                ],
            ),
            style="class:user",
            get_line_prefix=line_prefix,
            wrap_lines=True,
            dont_extend_height=True,
            height=Dimension(min=1, max=12),
        )
        self._picker_window = wheel_window(
            FormattedTextControl(lambda: ansi(self._pet_picker_rows()), focusable=True),
            dont_extend_height=True,
        )
        self._name_field = Window(BufferControl(self._name_buffer), height=1)
        self._system_prompt_field = Window(
            BufferControl(self._system_prompt_buffer),
            height=Dimension(min=1, max=12),
            wrap_lines=True,
            dont_extend_height=True,
        )
        settings = HSplit([
            Window(FormattedTextControl("Agent name"), height=1),
            self._name_field,
            Window(FormattedTextControl("System prompt"), height=1),
            self._system_prompt_field,
            ConditionalContainer(
                Window(FormattedTextControl(lambda: self._settings_error), height=1),
                Condition(lambda: bool(self._settings_error)),
            ),
        ])
        pager_header = VSplit([
            wheel_window(
                FormattedTextControl(lambda: ansi(["  " + sgr("T R A N S C R I P T", BOLD, self.color)])),
                height=1,
            ),
            wheel_window(
                FormattedTextControl(lambda: ansi([self._pager_status()])),
                height=1,
                align=WindowAlign.RIGHT,
            ),
        ])
        footer = VSplit([
            wheel_window(FormattedTextControl(lambda: ansi([self._footer_hints()])), height=1),
            wheel_window(
                FormattedTextControl(lambda: ansi([self._footer_status()])),
                height=1,
                align=WindowAlign.RIGHT,
            ),
        ])
        return Layout(
            HSplit([
                ConditionalContainer(pager_header, in_pager),
                ConditionalContainer(
                    wheel_window(
                        FormattedTextControl(lambda: ansi([sgr("─" * self._width(), DIM, self.color)])),
                        height=1,
                    ),
                    in_pager,
                ),
                self._history_window,
                ConditionalContainer(
                    wheel_window(FormattedTextControl(lambda: ansi([self._status_line()])), height=1),
                    is_running,
                ),
                ConditionalContainer(wheel_window(height=Dimension(preferred=1, max=1)), ~in_pager),
                ConditionalContainer(self._composer, in_composer),
                ConditionalContainer(
                    wheel_window(
                        FormattedTextControl(lambda: ansi(self._command_rows())),
                        dont_extend_height=True,
                    ),
                    has_commands,
                ),
                ConditionalContainer(self._picker_window, in_picker),
                ConditionalContainer(settings, in_settings),
                wheel_window(height=Dimension(preferred=1, max=1)),
                footer,
            ]),
            focused_element=self._composer,
        )

    def _status_line(self) -> str:
        elapsed = format_elapsed(time.monotonic() - self.turn_started)
        action = "esc to close" if self._in_pager else "esc to interrupt"
        return (
            "• "
            + shimmer("Working", time.monotonic(), self.color)
            + sgr(f" ({elapsed} • {action})", DIM, self.color)
        )

    def _pager_status(self) -> str:
        total = len(self._history.rows) + len(self.transcript.tail(separate_stream=True))
        if not total:
            label = "Empty"
        elif self._history.first_line is None:
            label = "Live" if self.running else "Bottom"
        elif self._history.first_line == 0:
            label = f"Top · 1/{total}"
        else:
            row = min(self._history.first_line + 1, total)
            label = f"Row {row}/{total}"
        return sgr(f"{label}  ", DIM, self.color)

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

        art = pet_rows(selected_name, self.color, true_color=self.transcript.true_color)
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
        if self._in_pager:
            hints = ["↑/↓ scroll", "PgUp/PgDn page", "Home/End jump", "q/esc back"]
        elif self._editing_settings:
            hints = ["tab switch field", "⌃S save", "esc cancel"]
        elif self._pet_picker_index is not None:
            hints = ["↑/↓ choose", "⏎ select", "esc cancel"]
        elif self.running:
            hints = ["esc interrupt", "⌃T transcript", "⌃C interrupt"]
        elif matching_commands(self.buffer.text):
            hints = ["tab complete", "⏎ run"]
        elif self.buffer.text:
            hints = ["⏎ send", "⌥⏎ newline", "⌃C clear"]
        else:
            hints = ["⏎ send", "⌥⏎ newline", "/ commands", "PgUp/PgDn scroll", "⌃T transcript", "⌃C quit"]
        return "  " + sgr("   ".join(hints), DIM, self.color)

    def _footer_status(self) -> str:
        parts = []
        if not self._in_pager and self._history.first_line is not None:
            parts.append("↑ scrolled")
        tokens = self.conversation.total_tokens()
        if tokens:
            parts.append(f"{format_tokens(tokens)} tokens used")
        return sgr(" · ".join(parts) + "  ", DIM, self.color) if parts else ""

    # Input handling

    def _handle_surface_wheel(self, direction: int) -> None:
        if self._pet_picker_index is not None and not self._in_pager:
            self._move_pet_picker(direction)
        else:
            self._scroll_wheel(direction)

    def _scroll_wheel(self, direction: int) -> None:
        if (direction < 0 < self._scroll_remainder) or (direction > 0 > self._scroll_remainder):
            self._scroll_remainder = 0.0
        total = self._scroll_remainder + direction * MOUSE_SCROLL_LINES * self.mouse_scroll_speed
        lines = int(total)
        self._scroll_remainder = total - lines
        if lines:
            self._scroll_lines(lines)

    def _scroll_lines(self, delta: int) -> None:
        info = self._history_window.render_info
        if info is None or not info.displayed_lines or delta == 0:
            return
        first = info.first_visible_line()
        last = info.last_visible_line()
        if delta < 0:
            if first == 0:
                return
            target = max(0, first + delta)
            self._history.first_line = target
            self._history_window.vertical_scroll = target
        elif last + delta >= info.content_height - 1:
            self._history.first_line = None
            self._scroll_remainder = 0.0
        else:
            target = first + delta
            self._history.first_line = target
            self._history_window.vertical_scroll = target
        self.app.invalidate()

    def _scroll_history(self, direction: int) -> None:
        info = self._history_window.render_info
        if info is None or not info.displayed_lines:
            return
        page = max(1, info.last_visible_line() - info.first_visible_line())
        self._scroll_lines(direction * page)

    def _scroll_half_page(self, direction: int) -> None:
        info = self._history_window.render_info
        if info is None or not info.displayed_lines:
            return
        half_page = max(1, (info.last_visible_line() - info.first_visible_line()) // 2)
        self._scroll_lines(direction * half_page)

    def _scroll_to_top(self) -> None:
        info = self._history_window.render_info
        if info is not None and info.content_height <= info.window_height:
            return
        self._history.first_line = 0
        self._history_window.vertical_scroll = 0
        self._scroll_remainder = 0.0
        self.app.invalidate()

    def _scroll_to_bottom(self) -> None:
        self._history.first_line = None
        self._scroll_remainder = 0.0
        self.app.invalidate()

    def _bindings(self) -> KeyBindings:
        bindings = KeyBindings()
        in_pager = Condition(lambda: self._in_pager)
        in_picker = ~in_pager & Condition(lambda: self._pet_picker_index is not None)
        in_settings = ~in_pager & Condition(lambda: self._editing_settings)
        in_name = in_settings & Condition(lambda: self.app.layout.has_focus(self._name_field))
        in_composer = ~in_pager & ~in_picker & ~in_settings

        @bindings.add("c-t", filter=~in_settings & ~in_picker)
        def toggle_pager(event):
            self._toggle_pager()

        @bindings.add(Keys.ScrollUp, filter=~in_settings)
        def wheel_up(event):
            self._handle_surface_wheel(-1)

        @bindings.add(Keys.ScrollDown, filter=~in_settings)
        def wheel_down(event):
            self._handle_surface_wheel(1)

        @bindings.add("pageup", filter=~in_settings)
        def page_up(event):
            self._scroll_history(-1)

        @bindings.add("pagedown", filter=~in_settings)
        def page_down(event):
            self._scroll_history(1)

        @bindings.add("c-home", filter=~in_settings)
        def transcript_top(event):
            self._scroll_to_top()

        @bindings.add("c-end", filter=~in_settings)
        def transcript_bottom(event):
            self._scroll_to_bottom()

        @bindings.add("up", filter=in_pager)
        @bindings.add("k", filter=in_pager)
        @bindings.add("c-p", filter=in_pager)
        @bindings.add("c-y", filter=in_pager)
        def pager_up(event):
            self._scroll_lines(-1)

        @bindings.add("down", filter=in_pager)
        @bindings.add("j", filter=in_pager)
        @bindings.add("c-n", filter=in_pager)
        @bindings.add("c-e", filter=in_pager)
        @bindings.add("enter", filter=in_pager)
        def pager_down(event):
            self._scroll_lines(1)

        @bindings.add("b", filter=in_pager)
        def pager_page_up(event):
            self._scroll_history(-1)

        @bindings.add(" ", filter=in_pager)
        def pager_page_down(event):
            self._scroll_history(1)

        @bindings.add("c-u", filter=in_pager)
        def pager_half_up(event):
            self._scroll_half_page(-1)

        @bindings.add("c-d", filter=in_pager)
        def pager_half_down(event):
            self._scroll_half_page(1)

        @bindings.add("home", filter=in_pager)
        @bindings.add("g", filter=in_pager)
        @bindings.add("<", filter=in_pager)
        def pager_top(event):
            self._scroll_to_top()

        @bindings.add("end", filter=in_pager)
        @bindings.add("G", filter=in_pager)
        @bindings.add(">", filter=in_pager)
        def pager_bottom(event):
            self._scroll_to_bottom()

        @bindings.add("q", filter=in_pager)
        @bindings.add("escape", eager=True, filter=in_pager)
        def pager_close(event):
            self._close_pager()

        @bindings.add("tab", filter=in_settings)
        @bindings.add("s-tab", filter=in_settings)
        def switch_field(event):
            field = self._system_prompt_field if in_name() else self._name_field
            self.app.layout.focus(field)

        @bindings.add("enter", filter=in_name)
        def focus_system_prompt(event):
            self.app.layout.focus(self._system_prompt_field)

        @bindings.add("c-s", filter=in_settings)
        def save_settings_editor(event):
            self._save_agent_settings()

        @bindings.add("escape", eager=True, filter=in_settings)
        def cancel_settings_editor(event):
            self._close_settings()

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

        @bindings.add("enter", filter=in_composer)
        def submit(event):
            self.submit()

        @bindings.add("escape", "enter", filter=in_composer)
        @bindings.add("c-j", filter=in_composer)
        def newline(event):
            self.buffer.insert_text("\n")

        @bindings.add("tab", filter=in_composer)
        def complete(event):
            matches = matching_commands(self.buffer.text)
            if matches:
                self.buffer.text = matches[0]
                self.buffer.cursor_position = len(self.buffer.text)

        # Eager so Esc interrupts at once instead of waiting to see whether it
        # starts a key sequence; only while running outside overlays, so Alt+Enter works when idle.
        @bindings.add("escape", eager=True, filter=in_composer & Condition(lambda: self.running))
        def escape(event):
            self.interrupt()

        @bindings.add("c-c")
        def control_c(event):
            if self._in_pager:
                self._close_pager()
            elif self._editing_settings:
                self._close_settings()
            elif self._pet_picker_index is not None:
                self._close_pet_picker()
            elif self.running:
                self.interrupt()
            elif self.buffer.text:
                self.buffer.reset()
            else:
                self.app.exit()

        @bindings.add("c-d", filter=in_composer)
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
        self.buffer.append_to_history()
        self.buffer.reset()
        self._scroll_to_bottom()
        cmd = parse_slash_command(prompt, interactive=True)
        if cmd is not None:
            if cmd.error:
                self.transcript.error(cmd.error)
            elif cmd.name == "/exit":
                self.app.exit()
            elif cmd.name == "/clear":
                try:
                    self.conversation.reset()
                except InvocationError as error:
                    self.transcript.error(str(error))
                    return
                del self._history.rows[self._header_len :]
                self._refresh_header()
                self.transcript.info("Started a new conversation.")
            elif cmd.name == "/settings":
                self._open_settings()
            elif cmd.name == "/pet":
                if cmd.arg is None:
                    self._open_pet_picker()
                else:
                    self._select_pet(cmd.arg)
            elif result := command_output(cmd.name, self.conversation):
                self.transcript.info(result)
            return
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
        stopped = False
        try:
            await self.conversation.invoke_async(prompt)
        except asyncio.CancelledError:
            if not self.stop_requested:
                raise
            stopped = True
        except InvocationError as error:
            self.transcript.error(str(error))
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
        self._header_width = self._width()
        info = session_info(self.conversation.details(), self._header_context)
        self.transcript.header(pet=self.pet, **info)
        self._header_len = len(self._history.rows) - start

    async def run_async(self) -> None:
        await self.app.run_async(pre_run=self._header)

    def run(self) -> None:
        asyncio.run(self.run_async())
