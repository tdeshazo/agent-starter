import asyncio
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest import mock

from prompt_toolkit.data_structures import Size
from prompt_toolkit.formatted_text import ANSI, fragment_list_to_text, to_formatted_text
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from prompt_toolkit.utils import get_cwidth

from simple_agent.tui import (
    DEFAULT_PET,
    PET_NAMES,
    AgentTui,
    StreamCell,
    Transcript,
    header_cell,
    load_pet,
    pet_rows,
    run_plain,
    sanitize_text,
    save_pet,
    session_info,
)
from simple_agent.tui.app import matching_commands
from simple_agent.tui.pets import PETS, settings_path
from simple_agent.tui.rendering import BOLD, DIM, session_box
from simple_agent.tui.session import total_tokens


class PetTests(unittest.TestCase):
    def test_all_pets_have_aligned_half_block_pixel_sprites_and_palettes(self):
        self.assertEqual(
            PET_NAMES,
            (
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
            ),
        )
        sprites = set()
        for name in PET_NAMES:
            pet = PETS[name]
            self.assertEqual(len(pet.pixels) % 2, 0)
            self.assertGreater(len(pet.pixels), 0)
            sprites.add(pet.pixels)
            for pixel_row in pet.pixels:
                self.assertEqual(len(pixel_row), pet.width)
                for key in pixel_row:
                    if key != ".":
                        self.assertIn(key, pet.palette)
            for color, true_color in ((False, False), (True, False), (True, True)):
                rendered = pet_rows(name, color=color, true_color=true_color)
                self.assertEqual(len(rendered), pet.height)
                for row in rendered:
                    plain = fragment_list_to_text(to_formatted_text(ANSI(row)))
                    self.assertEqual(get_cwidth(plain), pet.width)
        self.assertEqual(len(sprites), len(PET_NAMES))

    def test_header_renders_selected_pet_and_drops_it_when_narrow(self):
        for name in PET_NAMES:
            wide = header_cell("gemma-4-e4b", "127.0.0.1:8088/v1", "~/repo", "0.1.0", width=80, color=False, pet=name)
            for art_row, header_row in zip(pet_rows(name, color=False), wide):
                self.assertTrue(header_row.startswith(art_row))
            colored_256 = pet_rows(name, color=True, true_color=False)
            colored_24 = pet_rows(name, color=True, true_color=True)
            self.assertTrue(any("\x1b[38;5;" in line and ";48;5;" in line for line in colored_256))
            self.assertTrue(any("\x1b[38;2;" in line and ";48;2;" in line for line in colored_24))

        narrow = header_cell("gemma-4-e4b", "127.0.0.1:8088/v1", "~/repo", "0.1.0", width=45, color=False, pet="cat")
        self.assertTrue(narrow[0].startswith("╭"))

    def test_persistence_roundtrip_preserves_other_keys_and_handles_corrupt_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "simple-agent" / "settings.json"
            self.assertEqual(load_pet(config), DEFAULT_PET)

            config.parent.mkdir(parents=True)
            config.write_text('{"theme": "dark"}\n', encoding="utf-8")
            self.assertEqual(save_pet("  CAT ", config), "cat")
            self.assertEqual(load_pet(config), "cat")
            self.assertEqual(json.loads(config.read_text(encoding="utf-8")), {"theme": "dark", "pet": "cat"})

            self.assertEqual(save_pet("Hermit Crab", config), "hermit-crab")
            self.assertEqual(load_pet(config), "hermit-crab")

            config.write_text("{not valid json", encoding="utf-8")
            self.assertEqual(load_pet(config), DEFAULT_PET)

            config.write_text('{"pet": "dragon"}\n', encoding="utf-8")
            self.assertEqual(load_pet(config), DEFAULT_PET)

            with self.assertRaises(ValueError):
                save_pet("dragon", config)

    def test_settings_path_respects_xdg_config_home(self):
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/tmp/custom-xdg"}):
            self.assertEqual(settings_path(), Path("/tmp/custom-xdg/simple-agent/settings.json"))

    def test_matching_commands_supports_pet_arguments(self):
        self.assertIn("/pet", matching_commands("/"))
        self.assertEqual(
            matching_commands("/pet "),
            [
                "/pet frog",
                "/pet rabbit",
                "/pet cat",
                "/pet octopus",
                "/pet alien",
                "/pet robot",
                "/pet moth",
                "/pet axolotl",
                "/pet hermit-crab",
                "/pet ghost",
                "/pet snail",
                "/pet mimic",
            ],
        )
        self.assertEqual(matching_commands("/pet r"), ["/pet rabbit", "/pet robot"])
        self.assertEqual(matching_commands("/pet o"), ["/pet octopus"])
        self.assertEqual(matching_commands("/pet al"), ["/pet alien"])
        self.assertEqual(matching_commands("/pet m"), ["/pet moth", "/pet mimic"])
        self.assertEqual(matching_commands("/pet ax"), ["/pet axolotl"])
        self.assertEqual(matching_commands("/pet hermit c"), ["/pet hermit-crab"])
        self.assertEqual(matching_commands("/pet g"), ["/pet ghost"])
        self.assertEqual(matching_commands("/pet s"), ["/pet snail"])
        self.assertEqual(matching_commands("/pet mi"), ["/pet mimic"])
        self.assertEqual(matching_commands("/pet dog"), [])


class PlainModePetTests(unittest.TestCase):
    def test_plain_mode_selects_and_persists_pet(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "settings.json"
            inputs = iter(["/pet", "/pet dragon", "/pet rabbit", "/exit"])
            agent = SimpleNamespace(messages=[])
            output = io.StringIO()
            with redirect_stdout(output):
                run_plain(lambda: agent, read=lambda: next(inputs), config_path=config)

            rendered = output.getvalue()
            self.assertIn("Current pet: frog.", rendered)
            self.assertIn("Unknown pet 'dragon'", rendered)
            self.assertIn("Selected pet: rabbit.", rendered)
            self.assertEqual(load_pet(config), "rabbit")

    def test_plain_mode_handles_prefix_and_unknown_slash_commands_locally(self):
        invoked = []

        class StubAgent:
            def __init__(self):
                self.messages = []
                self.name = "Simple Agent"

            def __call__(self, prompt):
                invoked.append(prompt)

        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "settings.json"
            inputs = iter(["/help", "/clear extra", "/pet ax", "/st", "/etc/hosts explain this", "/ex"])
            output = io.StringIO()
            with redirect_stdout(output):
                run_plain(StubAgent, read=lambda: next(inputs), config_path=config)

            rendered = output.getvalue()
            self.assertIn("Unknown command /help. Available commands:", rendered)
            self.assertIn("Command /clear does not take arguments.", rendered)
            self.assertIn("Selected pet: axolotl.", rendered)
            self.assertIn("Provider:", rendered)
            self.assertEqual(invoked, ["/etc/hosts explain this"])
            self.assertEqual(load_pet(config), "axolotl")


class PackageMetadataTests(unittest.TestCase):
    def test_session_info_reports_installed_package_version(self):
        info = session_info(SimpleNamespace(messages=[]))
        self.assertEqual(info["app_version"], "0.1.0")
        header = "\n".join(header_cell(**info, width=80, color=False))
        self.assertIn("Simple Agent (v0.1.0)", header)


class TranscriptTests(unittest.TestCase):
    def test_wraps_streamed_words_and_indents_explicit_lines(self):
        rows = []
        transcript = Transcript(rows.extend, lambda: 15, color=False)
        for chunk in ("One two thr", "ee four\n\n  In", "dented line"):
            transcript(data=chunk)
        transcript.end_turn(0)

        self.assertEqual(rows, ["", "• One two three", "  four", "", "    Indented", "  line"])

    def test_tool_lines_stay_inside_the_agent_turn(self):
        rows = []
        transcript = Transcript(rows.extend, lambda: 80, color=False)
        transcript(data="Checking")
        transcript(message={"content": [{"toolUse": {
            "toolUseId": "1", "name": "current_time", "input": {},
        }}]})
        self.assertEqual(transcript.tail(), ["", "• Calling current_time({})"])
        transcript(message={"content": [{"toolResult": {
            "toolUseId": "1", "status": "success", "content": [{"text": "12:00"}],
        }}]})
        transcript(data="Done.\n")
        transcript.end_turn(1)

        self.assertEqual(rows[:-1], [
            "", "• Checking", "", "• Called current_time({})", "  └ 12:00", "", "• Done.", "",
        ])
        self.assertTrue(rows[-1].startswith("─ Worked for 1s "))

    def test_strips_ansi_and_osc_escapes_across_cells_and_split_stream_chunks(self):
        self.assertEqual(
            sanitize_text("ok\x1b[31mRED\x1b[0m\x1b]52;c;aGVsbG8=\x07\rspoof\x08!"),
            "okREDspoof!",
        )
        rows = []
        transcript = Transcript(rows.extend, lambda: 80, color=False)
        transcript.user("hi \x1b[32mgreen\x1b[0m")
        transcript(data="Hello \x1b")
        self.assertEqual(transcript.tail(), ["• Hello"])
        transcript(data="[31mWorld\x1b[0m and \x1b]52;c;ZXY=")
        transcript(data="aWw=\x07done")
        transcript(message={"content": [{"toolUse": {
            "toolUseId": "1", "name": "read\x1b[31m_file", "input": {"path": "a\x9b31mb.txt"},
        }}]})
        transcript(message={"content": [{"toolResult": {
            "toolUseId": "1",
            "status": "success",
            "content": [{"text": "safe\x1b]0;pwned\x07\r\n\x1b[2Jline2"}],
        }}]})
        transcript.end_turn(1)

        joined = "\n".join(rows)
        self.assertNotIn("\x1b", joined)
        self.assertNotIn("\x9b", joined)
        self.assertNotIn("\x07", joined)
        self.assertIn("› hi green", joined)
        self.assertIn("• Hello World and done", joined)
        self.assertIn("• Called read_file(", joined)
        self.assertIn("  └ safe", joined)
        self.assertIn("    line2", joined)

    def test_markdown_fences_handle_nested_backticks_tildes_and_inline_spans(self):
        cell = StreamCell(width=80, bullet="•", color=True, markdown=True)
        rows = cell.push(
            "````markdown\n"
            "```python\n"
            "**still literal**\n"
            "```\n"
            "````\n"
            "~~~sh\n"
            "**also literal**\n"
            "~~~\n"
            "```inline``` **bold**\n"
        )
        rows.extend(cell.finish())
        joined = "\n".join(rows)
        self.assertIn("  **still literal**", joined)
        self.assertIn("  **also literal**", joined)
        self.assertIn(f"\x1b[{BOLD}mbold\x1b[0m", joined)
        self.assertIn(f"\x1b[{DIM}m````markdown\x1b[0m", joined)
        self.assertIn(f"\x1b[{DIM}m~~~sh\x1b[0m", joined)

    def test_session_box_empty_fields_and_transcript_errors_and_usage(self):
        box = session_box(None, None, "", "0.1.0", width=80, color=False)
        self.assertEqual(len(box), 3)
        self.assertIn("Simple Agent (v0.1.0)", box[1])

        rows = []
        transcript = Transcript(rows.extend, lambda: 80, color=False)

        class APITimeoutError(Exception):
            pass

        class APIConnectionError(Exception):
            pass

        class HttpError(Exception):
            status_code = 502

        transcript.invocation_failed(TimeoutError())
        transcript.invocation_failed(APITimeoutError())
        transcript.invocation_failed(APIConnectionError())
        transcript.invocation_failed(HttpError())
        transcript.invocation_failed(RuntimeError("internal detail"))

        # Zero default usage from Strands should be ignored; real usage should sum.
        transcript(message={"metadata": {"usage": {"inputTokens": 0, "outputTokens": 0}}})
        transcript.end_turn(0.5)
        self.assertNotIn("in 0", "\n".join(rows))

        transcript(
            message={
                "metadata": {
                    "usage": {
                        "inputTokens": 1200,
                        "cacheReadInputTokens": 400,
                        "outputTokens": 85,
                    }
                }
            }
        )
        transcript.end_turn(0.5)
        joined = "\n".join(rows)
        self.assertIn("TimeoutError: Provider timed out", joined)
        self.assertIn("APITimeoutError: Provider timed out", joined)
        self.assertIn("APIConnectionError: Could not connect to model server", joined)
        self.assertIn("HttpError: Provider request failed (HTTP 502)", joined)
        self.assertIn("RuntimeError: The response failed. Try again.", joined)
        self.assertNotIn("internal detail", joined)
        self.assertIn("in 1.2K · cached 400 · out 85", joined)

        agent = SimpleNamespace(
            event_loop_metrics=SimpleNamespace(accumulated_usage={"totalTokens": 1685})
        )
        self.assertEqual(total_tokens(agent), 1685)
        self.assertEqual(total_tokens(SimpleNamespace()), 0)


class AgentTuiTests(unittest.IsolatedAsyncioTestCase):
    async def test_settings_editor_updates_the_next_turn_and_persists_after_clear(self):
        turns = asyncio.Queue()
        previous_turn = {"role": "assistant", "content": [{"text": "Earlier reply"}]}

        def make_agent(messages=None):
            agent = SimpleNamespace(name="Default", system_prompt="Default prompt", messages=messages or [])

            async def invoke(prompt):
                turns.put_nowait((prompt, agent.name, agent.system_prompt, agent.messages.copy()))

            agent.invoke_async = invoke
            return agent

        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "settings.json"
            save_pet("cat", config)
            with create_pipe_input() as terminal:
                tui = AgentTui(
                    make_agent, agent=make_agent([previous_turn]), input=terminal,
                    output=DummyOutput(), color=False, config_path=config,
                )
                app = asyncio.create_task(tui.run_async())
                try:
                    terminal.send_text(
                        "/settings\r\x01\x0bGuide\t\x01\x0bFirst line\rSecond line\x13"
                        "/settings\r\x01\x0bDiscard this\x03"
                        "First question\r"
                    )
                    self.assertEqual(
                        await asyncio.wait_for(turns.get(), timeout=2),
                        ("First question", "Guide", "First line\nSecond line", [previous_turn]),
                    )
                    terminal.send_text("/clear\rSecond question\r")
                    self.assertEqual(
                        await asyncio.wait_for(turns.get(), timeout=2),
                        ("Second question", "Guide", "First line\nSecond line", []),
                    )
                    terminal.send_text("/exit\r")
                    await asyncio.wait_for(app, timeout=2)
                finally:
                    if not app.done():
                        app.cancel()
                        await asyncio.gather(app, return_exceptions=True)

            self.assertEqual(
                json.loads(config.read_text(encoding="utf-8")),
                {"pet": "cat", "agent_name": "Guide", "system_prompt": "First line\nSecond line"},
            )
            header = "\n".join(tui._history.rows[:tui._header_len])
            self.assertIn("Guide", header)

    async def test_escape_stops_stream_and_restores_history(self):
        previous_turn = {"role": "assistant", "content": [{"text": "Earlier reply"}]}
        started = asyncio.Event()
        followed_up = asyncio.Event()
        follow_up_history = []

        async def invoke(prompt):
            if prompt == "follow-up":
                follow_up_history.extend(agent.messages)
                agent.callback_handler(data="Next reply")
                followed_up.set()
                return
            agent.messages.append({"role": "user", "content": [{"text": prompt}]})
            agent.callback_handler(data="Partial reply")
            started.set()
            await asyncio.Future()

        agent = SimpleNamespace(messages=[previous_turn], invoke_async=invoke)
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "settings.json"
            with create_pipe_input() as terminal:
                tui = AgentTui(
                    lambda: agent,
                    input=terminal,
                    output=DummyOutput(),
                    color=False,
                    config_path=config,
                )
                app = asyncio.create_task(tui.run_async())
                try:
                    terminal.send_text("interrupted\r")
                    await asyncio.wait_for(started.wait(), timeout=2)
                    terminal.send_bytes(b"\x1b")
                    await asyncio.wait_for(asyncio.shield(tui.task), timeout=2)
                    terminal.send_text("follow-up\r")
                    await asyncio.wait_for(followed_up.wait(), timeout=2)
                    terminal.send_text("/exit\r")
                    await asyncio.wait_for(app, timeout=2)
                finally:
                    if not app.done():
                        app.cancel()
                        await asyncio.gather(app, return_exceptions=True)

        self.assertEqual(follow_up_history, [previous_turn])
        transcript = "\n".join(tui._history.rows)
        self.assertIn("• Partial reply", transcript)
        self.assertIn("Response stopped", transcript)
        self.assertIn("• Next reply", transcript)

    async def test_pet_command_and_picker_update_header_and_persist_across_sessions(self):
        invoked = []

        async def invoke(prompt):
            invoked.append(prompt)

        agent = SimpleNamespace(messages=[], invoke_async=invoke)
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "settings.json"

            # Session 1: open interactive picker via /pet, arrow down to rabbit, confirm;
            # then test invalid pet and escape-cancel.
            with create_pipe_input() as terminal:
                tui = AgentTui(
                    lambda: agent,
                    input=terminal,
                    output=DummyOutput(),
                    color=False,
                    config_path=config,
                )
                app = asyncio.create_task(tui.run_async())
                try:
                    terminal.send_text("/pet\r")
                    await asyncio.sleep(0.05)
                    self.assertEqual(tui._pet_picker_index, 0)
                    terminal.send_bytes(b"\x1b[B")  # Down -> rabbit
                    await asyncio.sleep(0.05)
                    self.assertEqual(tui._pet_picker_index, 1)
                    terminal.send_text("\r")
                    await asyncio.sleep(0.05)
                    self.assertIsNone(tui._pet_picker_index)
                    self.assertEqual(tui.pet, "rabbit")

                    # Open picker again, move down to cat, then cancel with Esc.
                    terminal.send_text("/pet\r")
                    await asyncio.sleep(0.05)
                    terminal.send_bytes(b"\x1b[B")  # Down -> cat
                    await asyncio.sleep(0.05)
                    terminal.send_bytes(b"\x1b")  # Cancel
                    await asyncio.sleep(0.15)
                    self.assertIsNone(tui._pet_picker_index)
                    self.assertEqual(tui.pet, "rabbit")

                    # Invalid pet must not be sent to the agent.
                    terminal.send_text("/pet dragon\r")
                    await asyncio.sleep(0.05)
                    terminal.send_text("/exit\r")
                    await asyncio.wait_for(app, timeout=2)
                finally:
                    if not app.done():
                        app.cancel()
                        await asyncio.gather(app, return_exceptions=True)

            self.assertEqual(invoked, [])
            self.assertEqual(load_pet(config), "rabbit")
            self.assertTrue(tui._history.rows[1].startswith(pet_rows("rabbit", color=False)[1]))
            transcript = "\n".join(tui._history.rows)
            self.assertIn("Selected pet: rabbit.", transcript)
            self.assertIn("Unknown pet 'dragon'", transcript)

            # Session 2: starts with persisted rabbit, then switches directly to cat via /pet cat.
            with create_pipe_input() as terminal:
                tui2 = AgentTui(
                    lambda: agent,
                    input=terminal,
                    output=DummyOutput(),
                    color=False,
                    config_path=config,
                )
                app2 = asyncio.create_task(tui2.run_async())
                try:
                    await asyncio.sleep(0.05)
                    self.assertEqual(tui2.pet, "rabbit")
                    self.assertTrue(tui2._history.rows[1].startswith(pet_rows("rabbit", color=False)[1]))
                    terminal.send_text("/pet cat\r")
                    await asyncio.sleep(0.05)
                    self.assertEqual(tui2.pet, "cat")
                    self.assertTrue(tui2._history.rows[0].startswith(pet_rows("cat", color=False)[0]))
                    terminal.send_text("/exit\r")
                    await asyncio.wait_for(app2, timeout=2)
                finally:
                    if not app2.done():
                        app2.cancel()
                        await asyncio.gather(app2, return_exceptions=True)

            self.assertEqual(load_pet(config), "cat")

    async def test_tui_rejects_unknown_commands_and_extra_command_args_without_invoking_agent(self):
        invoked = []

        async def invoke(prompt):
            invoked.append(prompt)

        agent = SimpleNamespace(messages=[], invoke_async=invoke)
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "settings.json"
            with create_pipe_input() as terminal:
                tui = AgentTui(
                    lambda: agent,
                    input=terminal,
                    output=DummyOutput(),
                    color=False,
                    config_path=config,
                )
                app = asyncio.create_task(tui.run_async())
                try:
                    terminal.send_text("/unknown\r/status extra\r/ex\r")
                    await asyncio.wait_for(app, timeout=2)
                finally:
                    if not app.done():
                        app.cancel()
                        await asyncio.gather(app, return_exceptions=True)

        self.assertEqual(invoked, [])
        transcript = "\n".join(tui._history.rows)
        self.assertIn("Unknown command /unknown. Type / to see available commands.", transcript)
        self.assertIn("Command /status does not take arguments.", transcript)

    async def test_header_reflows_automatically_when_terminal_width_changes(self):
        class ResizableOutput(DummyOutput):
            def __init__(self, columns: int):
                self.columns = columns

            def get_size(self) -> Size:
                return Size(rows=24, columns=self.columns)

        output = ResizableOutput(columns=45)
        agent = SimpleNamespace(messages=[], invoke_async=lambda _p: asyncio.sleep(0))
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "settings.json"
            save_pet("cat", config)
            with create_pipe_input() as terminal:
                tui = AgentTui(
                    lambda: agent,
                    input=terminal,
                    output=output,
                    color=False,
                    config_path=config,
                )
                app = asyncio.create_task(tui.run_async())
                try:
                    await asyncio.sleep(0.05)
                    self.assertTrue(tui._history.rows[0].startswith("╭"))

                    output.columns = 80
                    tui._history.create_content(width=80, height=20)
                    self.assertTrue(
                        tui._history.rows[0].startswith(pet_rows("cat", color=False)[0])
                    )

                    output.columns = 45
                    tui._history.create_content(width=45, height=20)
                    self.assertTrue(tui._history.rows[0].startswith("╭"))

                    terminal.send_text("/exit\r")
                    await asyncio.wait_for(app, timeout=2)
                finally:
                    if not app.done():
                        app.cancel()
                        await asyncio.gather(app, return_exceptions=True)
