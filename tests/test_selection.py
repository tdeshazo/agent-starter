import asyncio
import io
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from prompt_toolkit.data_structures import Point, Size
from prompt_toolkit.formatted_text import fragment_list_to_text
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType, MouseModifier
from prompt_toolkit.output.vt100 import Vt100_Output

from simple_agent.agent import create_conversation
from simple_agent.settings import open_preferences
from simple_agent.tui.app import AgentTui
from simple_agent.tui.history import TranscriptControl


def mouse(control, kind, x, y, *, button=MouseButton.LEFT, modifiers=frozenset()):
    return control.mouse_handler(MouseEvent(Point(x, y), kind, button, modifiers))


def drag(control, start, end):
    mouse(control, MouseEventType.MOUSE_DOWN, *start)
    mouse(control, MouseEventType.MOUSE_MOVE, *end)
    mouse(control, MouseEventType.MOUSE_UP, *end)


def control_with_rows(*rows, **kwargs):
    control = TranscriptControl(lambda: [], **kwargs)
    control.rows.extend(rows)
    control.create_content(20, 10)
    return control


async def wait_until(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(0.01)


@asynccontextmanager
async def running_tui(rows, *, columns=20, invoke=None):
    agent = SimpleNamespace(messages=[])
    if invoke is not None:
        agent.invoke_async = invoke
    output = Vt100_Output(io.StringIO(), lambda: Size(rows=16, columns=columns))
    with tempfile.TemporaryDirectory() as tmp, create_pipe_input() as terminal:
        preferences = open_preferences(Path(tmp) / "settings.json")
        conversation = create_conversation(lambda: agent, preferences)
        tui = AgentTui(conversation, preferences, input=terminal, output=output, color=False)
        tui._history.rows.extend(rows)
        tui._history.first_line = 0
        # Keep this fixture focused on transcript hit testing, with no decorative header.
        with mock.patch.object(tui, "_header", lambda: None):
            app = asyncio.create_task(tui.run_async())
            try:
                await wait_until(lambda: tui._history_window.render_info is not None)
                yield tui, terminal
            finally:
                if not app.done():
                    tui.app.exit()
                await asyncio.wait_for(app, timeout=2)


def sgr_drag(terminal, start, end):
    """Send physical, one-based SGR coordinates through the real input parser."""
    terminal.send_bytes(
        f"\x1b[<0;{start[0]};{start[1]}M"
        f"\x1b[<32;{end[0]};{end[1]}M"
        f"\x1b[<0;{end[0]};{end[1]}m".encode()
    )


class TranscriptSelectionTests(unittest.TestCase):
    def test_drag_preserves_final_character_and_strips_ansi_in_both_directions(self):
        control = control_with_rows("prefix \x1b[1;31mred界\x1b[0m tail")
        for start, end in [((7, 0), (99, 0)), ((99, 0), (7, 0))]:
            with self.subTest(start=start):
                control.clear_selection()
                drag(control, start, end)
                self.assertEqual(control.selected_text(), "red界 tail")
                content = control.create_content(20, 10)
                selected = "".join(
                    text for style, text, *_ in content.get_line(0) if "class:selected" in style
                )
                self.assertEqual(selected, control.selected_text())

    def test_selection_uses_last_painted_rows_through_stream_commit(self):
        tail = ["stream before"]
        control = TranscriptControl(lambda: tail.copy())
        control.rows.append("first")
        control.create_content(20, 10)
        # New content arrives after paint but before the click, and the tail commits.
        control.rows.append("stream after")
        tail.clear()
        drag(control, (0, 1), (99, 1))
        self.assertEqual(control.selected_text(), "stream before")
        frozen = control.create_content(20, 10)
        self.assertEqual(fragment_list_to_text(frozen.get_line(1)), "stream before")
        control.clear_selection()
        latest = control.create_content(20, 10)
        self.assertEqual(fragment_list_to_text(latest.get_line(1)), "stream after")

    def test_click_without_drag_releases_frozen_rows(self):
        control = control_with_rows("old")
        mouse(control, MouseEventType.MOUSE_DOWN, 1, 0)
        control.rows.append("new")
        mouse(control, MouseEventType.MOUSE_UP, 1, 0)
        self.assertFalse(control.has_selection)
        self.assertEqual(control.selected_text(), "")
        self.assertEqual(control.create_content(20, 10).line_count, 2)

    def test_blank_rows_have_mouse_cells_but_no_copied_padding(self):
        control = control_with_rows("head", "", "tail")
        content = control.create_content(20, 10)
        self.assertEqual(fragment_list_to_text(content.get_line(1)), " ")
        drag(control, (0, 0), (99, 2))
        self.assertEqual(control.selected_text(), "head\n\ntail")

    def test_double_triple_and_shift_click_select_words_lines_and_ranges(self):
        control = control_with_rows("first second third", "last")
        with mock.patch("simple_agent.tui.history.time.monotonic", side_effect=[1.0, 1.1, 1.2]):
            for expected in ["", "second", "first second third"]:
                mouse(control, MouseEventType.MOUSE_DOWN, 8, 0)
                mouse(control, MouseEventType.MOUSE_UP, 8, 0)
                self.assertEqual(control.selected_text(), expected)
        mouse(
            control, MouseEventType.MOUSE_DOWN, 99, 1,
            modifiers=frozenset({MouseModifier.SHIFT}),
        )
        mouse(control, MouseEventType.MOUSE_UP, 99, 1)
        self.assertEqual(control.selected_text(), "first second third\nlast")

    def test_wheel_and_non_left_clicks_preserve_selection_without_taking_focus(self):
        wheel = mock.Mock()
        control = control_with_rows("copy me", on_wheel=wheel)
        drag(control, (0, 0), (99, 0))
        self.assertFalse(control.is_focusable())
        mouse(control, MouseEventType.SCROLL_UP, 0, 0, button=MouseButton.NONE)
        mouse(control, MouseEventType.SCROLL_DOWN, 0, 0, button=MouseButton.NONE)
        mouse(control, MouseEventType.MOUSE_DOWN, 0, 0, button=MouseButton.RIGHT)
        self.assertEqual(control.selected_text(), "copy me")
        self.assertEqual(wheel.call_args_list, [mock.call(-1), mock.call(1)])
        control.clear_selection()
        mouse(control, MouseEventType.MOUSE_DOWN, 0, 0)
        mouse(control, MouseEventType.MOUSE_MOVE, 3, 0, button=MouseButton.NONE)
        control.rows.append("still live")
        self.assertFalse(control.has_selection)
        self.assertEqual(control.create_content(20, 10).line_count, 2)

    def test_double_click_preserves_decomposed_accents_in_a_word(self):
        control = control_with_rows("e\u0301clair done")
        with mock.patch("simple_agent.tui.history.time.monotonic", side_effect=[1.0, 1.1]):
            for _ in range(2):
                mouse(control, MouseEventType.MOUSE_DOWN, 0, 0)
                mouse(control, MouseEventType.MOUSE_UP, 0, 0)
        self.assertEqual(control.selected_text(), "e\u0301clair")

    def test_zero_width_escape_payloads_are_not_selected_or_copied(self):
        control = control_with_rows("\x01invisible\x02\x1b[31mvisible\x1b[0m")
        drag(control, (0, 0), (99, 0))
        self.assertEqual(control.selected_text(), "visible")
        fragments = control.create_content(20, 10).get_line(0)
        self.assertEqual(fragment_list_to_text(fragments), "visible")
        self.assertTrue(any("[ZeroWidthEscape]" in style for style, *_ in fragments))


class SelectionIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_mouse_mapping_handles_wide_empty_and_soft_wrapped_rows(self):
        rows = ["ab界cd", "", "0123456789ABCDEFGHIJKLMN", "tail終"]
        async with running_tui(rows) as (tui, terminal):
            self.assertTrue(tui.app.renderer._mouse_support_enabled)
            # CJK takes two terminal cells; the blank row is physical row two.
            # The long logical row wraps from physical row three onto four.
            for start, end, expected in [
                ((3, 1), (19, 1), "界cd"),
                ((1, 2), (3, 4), "\n0123456789ABCDEFGHIJKLM"),
                ((19, 5), (1, 1), "\n".join(rows)),
            ]:
                with self.subTest(start=start, end=end):
                    tui._clear_selection()
                    tui.app.invalidate()
                    await asyncio.sleep(0.03)
                    sgr_drag(terminal, start, end)
                    await wait_until(lambda: tui._history.has_selection)
                    self.assertEqual(tui._history.selected_text(), expected)
                    self.assertTrue(tui.app.layout.has_focus(tui._composer))

    async def test_ctrl_c_copies_and_escape_clears_before_interrupting_running_turn(self):
        started = asyncio.Event()
        finish = asyncio.Event()

        async def invoke(_prompt):
            started.set()
            await finish.wait()

        copied = mock.AsyncMock(return_value="Copied selection.")
        with mock.patch("simple_agent.tui.app.copy_text", copied):
            async with running_tui(["copy while running"], invoke=invoke) as (tui, terminal):
                terminal.send_text("go\r")
                await asyncio.wait_for(started.wait(), timeout=2)
                await asyncio.sleep(0.03)
                sgr_drag(terminal, (1, 1), (19, 1))
                await wait_until(lambda: tui._history.has_selection)
                terminal.send_bytes(b"\x03")
                await wait_until(lambda: copied.await_count == 1)
                self.assertEqual(copied.call_args.args[0], "copy while running")
                self.assertTrue(tui.running)
                terminal.send_bytes(b"\x1b")
                await wait_until(lambda: not tui._history.has_selection)
                self.assertTrue(tui.running)
                terminal.send_bytes(b"\x03")
                await wait_until(lambda: not tui.running)
                self.assertTrue(tui.stop_requested)

    async def test_composer_copy_precedence_and_pending_copy_preserve_new_selection(self):
        copy_started = asyncio.Event()
        finish_copy = asyncio.Event()
        copied_text = []

        async def copy(text, _output):
            copied_text.append(text)
            copy_started.set()
            await finish_copy.wait()
            return "Copied selection."

        with mock.patch("simple_agent.tui.app.copy_text", copy):
            async with running_tui(["transcript first", "transcript second"]) as (tui, terminal):
                tui.buffer.text = "draft keep"
                drag(tui._history, (0, 0), (99, 0))
                tui.buffer.cursor_position = 0
                tui.buffer.start_selection()
                tui.buffer.cursor_position = 5
                terminal.send_bytes(b"\x03")
                await asyncio.wait_for(copy_started.wait(), timeout=2)
                self.assertEqual(copied_text, ["draft"])
                self.assertEqual(tui.buffer.text, "draft keep")
                drag(tui._history, (0, 1), (99, 1))
                finish_copy.set()
                await asyncio.wait_for(asyncio.shield(tui._copy_task), timeout=2)
                self.assertEqual(tui._history.selected_text(), "transcript second")
                self.assertIn("Copied", tui._copy_status)
                terminal.send_text("x")
                await wait_until(lambda: tui.buffer.text == "draftx keep")
                self.assertFalse(tui._history.has_selection)
                self.assertEqual(tui._copy_status, "")

    async def test_ctrl_insert_sequence_copies_selected_text(self):
        copied = mock.AsyncMock(return_value="Copied selection.")
        with mock.patch("simple_agent.tui.app.copy_text", copied):
            async with running_tui(["copy by keyboard"]) as (tui, terminal):
                sgr_drag(terminal, (1, 1), (19, 1))
                await wait_until(lambda: tui._history.has_selection)
                terminal.send_bytes(b"\x1b[2;5~")
                await wait_until(lambda: copied.await_count == 1)
                self.assertEqual(copied.call_args.args[0], "copy by keyboard")
                self.assertTrue(tui._history.has_selection)

    async def test_release_over_footer_unfreezes_click_and_preserves_dragged_selection(self):
        async with running_tui(["copy me"]) as (tui, terminal):
            terminal.send_bytes(b"\x1b[<0;2;1M")
            await wait_until(lambda: tui._history._dragging)
            terminal.send_bytes(b"\x1b[<0;2;16m")  # Release over the footer.
            await wait_until(lambda: not tui._history._dragging)
            self.assertFalse(tui._history.has_selection)
            tui._emit(["arrived after release"])
            await wait_until(lambda: tui._history_window.render_info.ui_content.line_count == 2)
            content = tui._history_window.render_info.ui_content
            self.assertEqual(fragment_list_to_text(content.get_line(1)), "arrived after release")

            # A real range remains selected when its drag ends on another surface.
            terminal.send_bytes(b"\x1b[<0;2;1M\x1b[<32;4;1M")
            await wait_until(lambda: tui._history.selected_text() == "opy")
            terminal.send_bytes(b"\x1b[<0;2;16m")
            await wait_until(lambda: not tui._history._dragging)
            self.assertEqual(tui._history.selected_text(), "opy")
            terminal.send_bytes(b"\x1b")
            await wait_until(lambda: not tui._history.has_selection)
            tui._emit(["live again"])
            await wait_until(lambda: tui._history_window.render_info.ui_content.line_count == 3)

    async def test_second_copy_request_waits_for_first_and_reports_latest_result(self):
        first_started = asyncio.Event()
        finish_first = asyncio.Event()
        copied_text = []

        async def copy(text, _output):
            copied_text.append(text)
            if len(copied_text) == 1:
                first_started.set()
                await finish_first.wait()
            return f"Copied {text}."

        with mock.patch("simple_agent.tui.app.copy_text", copy):
            async with running_tui(["first selection", "second selection"]) as (tui, terminal):
                sgr_drag(terminal, (1, 1), (19, 1))
                await wait_until(lambda: tui._history.has_selection)
                terminal.send_bytes(b"\x03")
                await asyncio.wait_for(first_started.wait(), timeout=2)
                sgr_drag(terminal, (1, 2), (19, 2))
                await wait_until(lambda: tui._history.selected_text() == "second selection")
                terminal.send_bytes(b"\x03")
                await asyncio.sleep(0.03)
                self.assertEqual(copied_text, ["first selection"])
                finish_first.set()
                await wait_until(lambda: len(copied_text) == 2)
                await asyncio.wait_for(asyncio.shield(tui._copy_task), timeout=2)
                self.assertEqual(copied_text, ["first selection", "second selection"])
                self.assertEqual(tui._copy_status, "Copied second selection.")
                self.assertEqual(tui._history.selected_text(), "second selection")
