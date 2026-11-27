import asyncio
import base64
import io
import os
import subprocess
import unittest
from unittest import mock

from prompt_toolkit.data_structures import Size
from prompt_toolkit.output import DummyOutput
from prompt_toolkit.output.plain_text import PlainTextOutput
from prompt_toolkit.output.vt100 import Vt100_Output

from simple_agent.tui.clipboard import OSC52_MAX_RAW_BYTES, copy_text


class TerminalBuffer(io.StringIO):
    def isatty(self):
        return True


class ClipboardTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.environment = mock.patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.platform = mock.patch("simple_agent.tui.clipboard.sys.platform", "linux")
        self.platform.start()
        self.addCleanup(self.platform.stop)
        self.buffer = TerminalBuffer()
        self.output = Vt100_Output(self.buffer, lambda: Size(rows=24, columns=80))

    async def test_native_writer_receives_unicode_on_stdin_and_no_terminal_escape(self):
        selection = "Café 漢字\n$(touch unexpected) `literal`"
        with (
            mock.patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}),
            mock.patch("simple_agent.tui.clipboard.shutil.which", return_value="/usr/bin/wl-copy"),
            mock.patch("simple_agent.tui.clipboard.subprocess.run") as run,
        ):
            self.assertEqual(await copy_text(selection, self.output), "Copied selection.")
        run.assert_called_once_with(
            ["/usr/bin/wl-copy", "--type", "text/plain;charset=utf-8"],
            input=selection.encode("utf-8"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=1.0,
            check=True,
        )
        self.assertEqual(self.buffer.getvalue(), "")

    async def test_failed_native_writer_falls_back_to_osc52(self):
        selection = "Café 漢字\nSecond line"
        with (
            mock.patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}),
            mock.patch("simple_agent.tui.clipboard.shutil.which", return_value="/usr/bin/wl-copy"),
            mock.patch(
                "simple_agent.tui.clipboard.subprocess.run",
                side_effect=subprocess.TimeoutExpired("wl-copy", 1),
            ),
        ):
            status = await copy_text(selection, self.output)
        self.assertEqual(status, "Sent selection to terminal clipboard.")
        encoded = base64.b64encode(selection.encode("utf-8")).decode("ascii")
        self.assertEqual(self.buffer.getvalue(), f"\x1b]52;c;{encoded}\x07")

    async def test_wsl_writer_uses_unicode_with_bom(self):
        with (
            mock.patch.dict(os.environ, {"WSL_DISTRO_NAME": "Ubuntu"}),
            mock.patch("simple_agent.tui.clipboard.shutil.which", return_value="/mnt/c/clip.exe"),
            mock.patch("simple_agent.tui.clipboard.subprocess.run") as run,
        ):
            self.assertEqual(await copy_text("Café 漢字", self.output), "Copied selection.")
        self.assertEqual(run.call_args.args[0], ["/mnt/c/clip.exe"])
        self.assertEqual(run.call_args.kwargs["input"], "Café 漢字".encode("utf-16"))
        self.assertEqual(self.buffer.getvalue(), "")

    async def test_tmux_wraps_osc52_with_escaped_dcs_passthrough(self):
        with mock.patch.dict(os.environ, {"TMUX": "/tmp/tmux-session"}):
            status = await copy_text("hello", self.output)
        self.assertEqual(status, "Sent selection to terminal clipboard.")
        self.assertEqual(self.buffer.getvalue(), "\x1bPtmux;\x1b\x1b]52;c;aGVsbG8=\x07\x1b\\")

    async def test_plain_dummy_and_redirected_outputs_do_not_claim_delivery(self):
        redirected = io.StringIO()
        for output in (
            DummyOutput(),
            PlainTextOutput(redirected),
            Vt100_Output(redirected, lambda: Size(rows=24, columns=80)),
        ):
            with self.subTest(output=type(output).__name__):
                self.assertIn("Clipboard unavailable", await copy_text("hello", output))
        self.assertEqual(redirected.getvalue(), "")

    async def test_osc52_limit_counts_utf8_bytes_and_does_not_truncate(self):
        self.assertIn(
            "too large", await copy_text("漢" * (OSC52_MAX_RAW_BYTES // 3 + 1), self.output)
        )
        self.assertEqual(self.buffer.getvalue(), "")

    async def test_terminal_write_failure_is_reported(self):
        with mock.patch.object(self.output, "write_raw", side_effect=OSError("closed")):
            self.assertIn("Could not copy", await copy_text("hello", self.output))
        self.assertEqual(self.buffer.getvalue(), "")

    async def test_empty_selection_does_not_clear_clipboard(self):
        with mock.patch("simple_agent.tui.clipboard._copy_native") as native:
            self.assertEqual(await copy_text("", self.output), "Select text to copy.")
        native.assert_not_called()
        self.assertEqual(self.buffer.getvalue(), "")

    async def test_native_copy_does_not_block_event_loop(self):
        started = asyncio.Event()
        release = asyncio.Event()
        loop = asyncio.get_running_loop()

        def native(_text):
            loop.call_soon_threadsafe(started.set)
            asyncio.run_coroutine_threadsafe(release.wait(), loop).result(timeout=2)
            return True

        with mock.patch("simple_agent.tui.clipboard._copy_native", side_effect=native):
            task = asyncio.create_task(copy_text("hello", self.output))
            try:
                await asyncio.wait_for(started.wait(), timeout=1)
                self.assertFalse(task.done())
            finally:
                release.set()
            self.assertEqual(await asyncio.wait_for(task, timeout=1), "Copied selection.")
