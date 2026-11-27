import asyncio
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from prompt_toolkit.data_structures import Size
from prompt_toolkit.formatted_text import ANSI, fragment_list_to_text, to_formatted_text
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from prompt_toolkit.output.vt100 import Vt100_Output
from prompt_toolkit.utils import get_cwidth

from simple_agent.agent import create_conversation
from simple_agent.conversation import TextDelta
from simple_agent.settings import open_preferences, settings_path
from simple_agent.strands_backend import StrandsBackend, invocation_error, strands_callback
from simple_agent.tui import (
    DEFAULT_PET,
    PET_NAMES,
    AgentTui as ConversationTui,
    StreamCell,
    Transcript,
    header_cell,
    load_pet,
    pet_rows,
    run_plain as run_plain_conversation,
    sanitize_text,
    save_pet,
    session_info,
)
from simple_agent.tui.app import matching_commands
from simple_agent.tui.pets import PETS
from simple_agent.tui.rendering import (
    BOLD_CYAN,
    BOLD_RED,
    BOLD_RED_LIGHT,
    CYAN,
    DIM,
    USER_TEXT,
    USER_TEXT_LIGHT,
    session_box,
)


def build_tui(agent_factory, *, config_path, agent=None, **options):
    preferences = open_preferences(config_path)
    conversation = create_conversation(agent_factory, preferences, agent=agent)
    return ConversationTui(conversation, preferences, **options)


def run_plain(agent_factory, *, read, config_path):
    preferences = open_preferences(config_path)
    conversation = create_conversation(agent_factory, preferences)
    run_plain_conversation(conversation, preferences, read=read)


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
                "crt",
                "ooze",
                "orb",
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
                "/pet crt",
                "/pet ooze",
                "/pet orb",
            ],
        )
        self.assertEqual(matching_commands("/pet r"), ["/pet rabbit", "/pet robot"])
        self.assertEqual(matching_commands("/pet c"), ["/pet cat", "/pet crt"])
        self.assertEqual(matching_commands("/pet cr"), ["/pet crt"])
        self.assertEqual(matching_commands("/pet o"), ["/pet octopus", "/pet ooze", "/pet orb"])
        self.assertEqual(matching_commands("/pet oo"), ["/pet ooze"])
        self.assertEqual(matching_commands("/pet or"), ["/pet orb"])
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
        info = session_info(StrandsBackend(SimpleNamespace(messages=[])).details())
        self.assertEqual(info["app_version"], "0.1.0")
        header = "\n".join(header_cell(**info, width=80, color=False))
        self.assertIn("Simple Agent (v0.1.0)", header)


class TranscriptTests(unittest.TestCase):
    def test_wraps_streamed_words_and_indents_explicit_lines(self):
        rows = []
        transcript = Transcript(rows.extend, lambda: 15, color=False)
        for chunk in ("One two thr", "ee four\n\n  In", "dented line"):
            strands_callback(transcript)(data=chunk)
        transcript.end_turn(0)

        self.assertEqual(rows, ["", "• One two three", "  four", "", "    Indented", "  line"])

    def test_tool_lines_stay_inside_the_agent_turn(self):
        rows = []
        transcript = Transcript(rows.extend, lambda: 80, color=False)
        strands_callback(transcript)(data="Checking")
        strands_callback(transcript)(message={"content": [{"toolUse": {
            "toolUseId": "1", "name": "current_time", "input": {},
        }}]})
        self.assertEqual(transcript.tail(), ["", "• Calling current_time({})"])
        strands_callback(transcript)(message={"content": [{"toolResult": {
            "toolUseId": "1", "status": "success", "content": [{"text": "12:00"}],
        }}]})
        strands_callback(transcript)(data="Done.\n")
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
        strands_callback(transcript)(data="Hello \x1b")
        self.assertEqual(transcript.tail(), ["• Hello"])
        strands_callback(transcript)(data="[31mWorld\x1b[0m and \x1b]52;c;ZXY=")
        strands_callback(transcript)(data="aWw=\x07done")
        strands_callback(transcript)(message={"content": [{"toolUse": {
            "toolUseId": "1", "name": "read\x1b[31m_file", "input": {"path": "a\x9b31mb.txt"},
        }}]})
        strands_callback(transcript)(message={"content": [{"toolResult": {
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

    def test_user_text_is_styled_distinctly_from_agent_response_text(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"COLORFGBG": "15;0"}):
            config = Path(tmp) / "settings.json"
            rows = []
            transcript = Transcript(rows.extend, lambda: 20, color=True)
            transcript.user("First line wraps here\n\nSecond paragraph")
            strands_callback(transcript)(data="Agent reply wraps here")
            transcript.end_turn(0)

            tui = build_tui(
                lambda: SimpleNamespace(messages=[]),
                output=DummyOutput(),
                color=True,
                config_path=config,
            )
            self.assertEqual(tui.app.style.get_attrs_for_style_str("class:user").color, "afd7d7")
            self.assertEqual(tui.app.style.get_attrs_for_style_str("class:user class:prompt").color, "ansicyan")
            self.assertEqual(
                tui.app.style.get_attrs_for_style_str("class:user class:placeholder").color,
                "ansibrightblack",
            )

        self.assertEqual(
            rows,
            [
                "",
                f"\x1b[{BOLD_CYAN}m›\x1b[0m \x1b[{USER_TEXT}mFirst line wraps\x1b[0m",
                f"  \x1b[{USER_TEXT}mhere\x1b[0m",
                "  ",
                f"  \x1b[{USER_TEXT}mSecond paragraph\x1b[0m",
                "",
                "• Agent reply wraps",
                "  here",
            ],
        )

        with mock.patch.dict(os.environ, {"COLORFGBG": "0;15"}):
            light_rows = []
            light_transcript = Transcript(light_rows.extend, lambda: 80, color=True)
            light_transcript.user("Hello")
            self.assertEqual(
                light_rows,
                ["", f"\x1b[{BOLD_CYAN}m›\x1b[0m \x1b[{USER_TEXT_LIGHT}mHello\x1b[0m"],
            )

    def test_markdown_fences_handle_nested_backticks_tildes_and_inline_spans(self):
        with mock.patch.dict(os.environ, {"COLORFGBG": "15;0"}):
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
                "```inline``` **bold** ***both*** **with `code`**\n"
            )
            rows.extend(cell.finish())
        joined = "\n".join(rows)
        self.assertIn("  **still literal**", joined)
        self.assertIn("  **also literal**", joined)
        self.assertIn(f"\x1b[{CYAN}minline\x1b[0m", joined)
        self.assertIn(f"\x1b[{BOLD_RED}mbold\x1b[0m", joined)
        self.assertIn(f"\x1b[{BOLD_RED};3mboth\x1b[0m", joined)
        self.assertIn(f"\x1b[{BOLD_CYAN}mcode\x1b[0m", joined)
        self.assertIn(f"\x1b[{DIM}m````markdown\x1b[0m", joined)
        self.assertIn(f"\x1b[{DIM}m~~~sh\x1b[0m", joined)

        with mock.patch.dict(os.environ, {"COLORFGBG": "0;15"}):
            light_cell = StreamCell(width=80, bullet="•", color=True, markdown=True, light=True)
            light_rows = light_cell.push("**bold**\n") + light_cell.finish()
        self.assertIn(f"\x1b[{BOLD_RED_LIGHT}mbold\x1b[0m", "\n".join(light_rows))

    def test_markdown_lists_render_bullets_nesting_tasks_and_hanging_indents(self):
        # Leading list suppresses duplicate assistant turn bullet on row 0.
        lead_rows = []
        lead = Transcript(lead_rows.extend, lambda: 34, color=False)
        lead(TextDelta(
            (
                "*   **First**: wraps cleanly under the item text\n"
                "    *   Nested star item that also wraps cleanly\n"
                "        +   Third-level item\n"
                "- [x] Finished task\n"
                "- [ ] Pending task that wraps onto the next row\n\n"
                "1.  Ordered step that wraps onto a second line\n"
                "    Continuation line under step one\n"
                "10. Double-digit step that wraps onto a second line\n\n"
                "* * *\n\n"
                "Closing paragraph at root margin.\n"
            )
        ))
        lead.end_turn(0)

        self.assertEqual(
            lead_rows,
            [
                "",
                "  • First: wraps cleanly under the",
                "    item text",
                "    ◦ Nested star item that also",
                "      wraps cleanly",
                "      ▪ Third-level item",
                "  ☑ Finished task",
                "  ☐ Pending task that wraps onto",
                "    the next row",
                "",
                "  1. Ordered step that wraps onto",
                "     a second line",
                "     Continuation line under step",
                "     one",
                "  10. Double-digit step that wraps",
                "      onto a second line",
                "",
                "  " + "─" * 32,
                "",
                "  Closing paragraph at root",
                "  margin.",
            ],
        )

    def test_markdown_tables_align_columns_wrap_cells_and_preserve_code_pipes(self):
        md = (
            "| Setting | Default | Override |\n"
            "| :--- | :---: | ---: |\n"
            "| **Vulkan** host memory | `str | None` | `a \\| b` |\n"
            "| Escaped \\| pipe | - Local<br>- Fast wrap check | 日本語 |\n"
        )
        for width in (78, 44, 22, 12):
            rows = []
            transcript = Transcript(rows.extend, lambda w=width: w, color=True)
            strands_callback(transcript)(data=md)
            transcript.end_turn(0)
            plain_rows = [
                fragment_list_to_text(to_formatted_text(ANSI(row)))
                for row in rows
                if row
            ]
            for plain in plain_rows:
                self.assertLessEqual(get_cwidth(plain), width, plain)
            joined_plain = "\n".join(plain_rows)
            if width == 78:
                self.assertIn("str | None", joined_plain)
                self.assertIn("a | b", joined_plain)
                self.assertIn("Escaped | pipe", joined_plain)
            if width >= 44:
                self.assertIn("日本語", joined_plain)
            else:
                self.assertIn("日本", joined_plain)
                self.assertIn("語", joined_plain)
            self.assertNotIn("a \\| b", joined_plain)
            self.assertNotIn("Escaped \\|", joined_plain)
            if width >= 22:
                self.assertTrue(plain_rows[0].startswith("  ╭"))
                self.assertTrue(plain_rows[-1].startswith("  ╰"))
                # Every row of a bordered table has identical display width.
                widths = {get_cwidth(r) for r in plain_rows}
                self.assertEqual(len(widths), 1)

        # Prose containing pipes is not misidentified as a table.
        prose_rows = []
        prose = Transcript(prose_rows.extend, lambda: 60, color=False)
        prose(TextDelta("Run cmd1 | cmd2 in bash\nNext line of output\n"))
        prose.end_turn(0)
        self.assertEqual(
            prose_rows,
            ["", "• Run cmd1 | cmd2 in bash", "  Next line of output"],
        )

    def test_markdown_streaming_char_by_char_matches_batch_and_previews_live_tail(self):
        doc = (
            "## Overview\n\n"
            "Keep `snake_case`, 2 * 3 * 4, `src/*.py` vs tests/*.py, and def f(**kw, **other).\n"
            "Style *italic*, **bold**, ***both***, ~~strike~~, and [Guide](https://example.com/a_b).\n\n"
            "> Quote with **bold** and wrapped words:\n"
            "> - Quoted bullet one\n"
            ">   - Quoted nested bullet\n\n"
            "| Col A | Col B |\n"
            "| --- | ---: |\n"
            "| alpha | 42 |\n"
            "| beta | 100 |\n"
        )
        batch_rows = []
        batch = Transcript(batch_rows.extend, lambda: 52, color=True)
        batch(TextDelta(doc))
        batch.end_turn(0)

        streamed_rows = []
        saw_live_table = False
        streamed = Transcript(streamed_rows.extend, lambda: 52, color=True)
        for char in doc:
            streamed(TextDelta(char))
            tail = streamed.tail()
            for row in tail:
                plain = fragment_list_to_text(to_formatted_text(ANSI(row)))
                self.assertLessEqual(get_cwidth(plain), 52)
                if "╭" in plain:
                    saw_live_table = True
        streamed.end_turn(0)

        self.assertTrue(saw_live_table)
        self.assertEqual(streamed_rows, batch_rows)
        joined_plain = "\n".join(
            fragment_list_to_text(to_formatted_text(ANSI(row))) for row in streamed_rows
        )
        self.assertIn("2 * 3 * 4", joined_plain)
        self.assertIn("def f(**kw, **other)", joined_plain)
        self.assertIn("Guide", joined_plain)
        self.assertIn("(https://example.com/a_b)", joined_plain)

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

        transcript.error(str(invocation_error(TimeoutError())))
        transcript.error(str(invocation_error(APITimeoutError())))
        transcript.error(str(invocation_error(APIConnectionError())))
        transcript.error(str(invocation_error(HttpError())))
        transcript.error(str(invocation_error(RuntimeError("internal detail"))))

        # Zero default usage from Strands should be ignored; real usage should sum.
        strands_callback(transcript)(message={"metadata": {"usage": {"inputTokens": 0, "outputTokens": 0}}})
        transcript.end_turn(0.5)
        self.assertNotIn("in 0", "\n".join(rows))

        strands_callback(transcript)(
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
        self.assertEqual(StrandsBackend(agent).total_tokens(), 1685)
        self.assertEqual(StrandsBackend(SimpleNamespace()).total_tokens(), 0)


class AgentTuiTests(unittest.IsolatedAsyncioTestCase):
    async def test_clear_removes_transcript_and_starts_new_conversation(self):
        old_agent = SimpleNamespace(messages=[{"role": "user", "content": []}])
        new_agent = SimpleNamespace(messages=[])
        with tempfile.TemporaryDirectory() as tmp, create_pipe_input() as terminal:
            tui = build_tui(
                lambda: new_agent, agent=old_agent, input=terminal,
                output=DummyOutput(), color=False, config_path=Path(tmp) / "settings.json",
            )
            tui._header()
            tui.transcript.user("Previous question")
            tui.transcript.info("Previous response")
            tui._history.first_line = 0

            tui.buffer.text = "/clear"
            tui.submit()

            rendered = "\n".join(tui._history.rows)
            self.assertNotIn("Previous question", rendered)
            self.assertNotIn("Previous response", rendered)
            self.assertIn("Started a new conversation.", rendered)
            self.assertEqual(new_agent.messages, [])
            self.assertTrue(callable(new_agent.callback_handler))
            self.assertIsNone(tui._history.first_line)
            self.assertGreater(tui._header_len, 0)

            tui.transcript.user("New question")
            self.assertIn("New question", "\n".join(tui._history.rows))

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
                tui = build_tui(
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
                tui = build_tui(
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
                tui = build_tui(
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
                tui2 = build_tui(
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
                tui = build_tui(
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
                tui = build_tui(
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

    async def test_fullscreen_mouse_wheel_sticky_follow_and_jump_shortcuts(self):
        stream_ready = asyncio.Event()
        more_chunks = asyncio.Event()
        finish_turn = asyncio.Event()

        async def invoke(_prompt):
            agent.callback_handler(
                data="".join(f"Line {index:02d}\n" for index in range(1, 31))
            )
            stream_ready.set()
            await more_chunks.wait()
            agent.callback_handler(data="Streamed while scrolled up\n")
            await finish_turn.wait()

        agent = SimpleNamespace(messages=[], invoke_async=invoke)
        buf = io.StringIO()
        vt_output = Vt100_Output(buf, lambda: Size(rows=14, columns=80))
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "settings.json"
            config.write_text('{"mouse_scroll_speed": 0.5}\n', encoding="utf-8")
            with create_pipe_input() as terminal:
                tui = build_tui(
                    lambda: agent,
                    input=terminal,
                    output=vt_output,
                    color=False,
                    config_path=config,
                )
                self.assertTrue(tui.app.full_screen)
                app = asyncio.create_task(tui.run_async())
                try:
                    await asyncio.sleep(0.05)
                    self.assertTrue(tui.app.renderer._in_alternate_screen)
                    self.assertTrue(tui.app.renderer._mouse_support_enabled)

                    terminal.send_text("Generate lines\r")
                    await asyncio.wait_for(stream_ready.wait(), timeout=2)
                    await asyncio.sleep(0.05)
                    self.assertIsNone(tui._history.first_line)

                    # Clicking the transcript does not steal keyboard focus from the composer.
                    self.assertTrue(tui.app.layout.has_focus(tui._composer))
                    self.assertFalse(tui._history.is_focusable())

                    # Fractional mouse_scroll_speed (0.5 * 3 = 1.5) accumulates smoothly:
                    # tick 1 scrolls 1 row, tick 2 scrolls 2 rows (total 3 rows).
                    sgr_wheel_up = b"\x1b[<64;10;2M"
                    terminal.send_bytes(sgr_wheel_up)
                    await asyncio.sleep(0.05)
                    first_after_one_tick = tui._history.first_line
                    self.assertIsNotNone(first_after_one_tick)
                    terminal.send_bytes(sgr_wheel_up)
                    await asyncio.sleep(0.05)
                    self.assertEqual(tui._history.first_line, first_after_one_tick - 2)
                    self.assertIn("↑ scrolled", tui._footer_status())

                    # Wheel events over the pinned composer also scroll the transcript when
                    # the composer itself does not overflow.
                    before_composer_wheel = tui._history.first_line
                    terminal.send_bytes(b"\x1b[<64;5;12M")
                    await asyncio.sleep(0.05)
                    self.assertLess(tui._history.first_line, before_composer_wheel)

                    # Ctrl+Home jumps to top; streaming new lines preserves the reading position.
                    terminal.send_bytes(b"\x1b[1;5H")
                    await asyncio.sleep(0.05)
                    self.assertEqual(tui._history.first_line, 0)
                    more_chunks.set()
                    await asyncio.sleep(0.05)
                    self.assertEqual(tui._history.first_line, 0)

                    # Ctrl+End jumps back to bottom and re-engages live follow mode.
                    terminal.send_bytes(b"\x1b[1;5F")
                    await asyncio.sleep(0.05)
                    self.assertIsNone(tui._history.first_line)
                    self.assertNotIn("↑ scrolled", tui._footer_status())

                    finish_turn.set()
                    await asyncio.wait_for(asyncio.shield(tui.task), timeout=2)
                    terminal.send_text("/exit\r")
                    await asyncio.wait_for(app, timeout=2)
                finally:
                    more_chunks.set()
                    finish_turn.set()
                    if not app.done():
                        app.cancel()
                        await asyncio.gather(app, return_exceptions=True)

    async def test_ctrl_t_transcript_overlay_supports_vim_keys_and_preserves_running_turn(self):
        stream_ready = asyncio.Event()
        finish_turn = asyncio.Event()

        async def invoke(_prompt):
            agent.callback_handler(
                data="".join(f"Row {index:02d}\n" for index in range(1, 26))
            )
            stream_ready.set()
            await finish_turn.wait()

        agent = SimpleNamespace(messages=[], invoke_async=invoke)
        buf = io.StringIO()
        vt_output = Vt100_Output(buf, lambda: Size(rows=12, columns=80))
        with tempfile.TemporaryDirectory() as tmp, create_pipe_input() as terminal:
            tui = build_tui(
                lambda: agent,
                input=terminal,
                output=vt_output,
                color=False,
                config_path=Path(tmp) / "settings.json",
            )
            app = asyncio.create_task(tui.run_async())
            try:
                terminal.send_text("Inspect overlay\r")
                await asyncio.wait_for(stream_ready.wait(), timeout=2)
                await asyncio.sleep(0.05)

                # Ctrl+T enters transcript focus mode; g/j/k/G navigate without typing into buffer.
                terminal.send_bytes(b"\x14")
                await asyncio.sleep(0.05)
                self.assertTrue(tui._in_pager)
                self.assertTrue(tui._history.is_focusable())

                terminal.send_text("g")
                await asyncio.sleep(0.05)
                self.assertEqual(tui._history.first_line, 0)
                terminal.send_text("jjk")
                await asyncio.sleep(0.05)
                self.assertEqual(tui._history.first_line, 1)
                self.assertEqual(tui.buffer.text, "")

                terminal.send_text("G")
                await asyncio.sleep(0.05)
                self.assertIsNone(tui._history.first_line)

                # Esc exits the overlay back to the composer without cancelling the running turn.
                terminal.send_bytes(b"\x1b")
                await asyncio.sleep(0.15)
                self.assertFalse(tui._in_pager)
                self.assertTrue(tui.running)
                self.assertTrue(tui.app.layout.has_focus(tui._composer))

                finish_turn.set()
                await asyncio.wait_for(asyncio.shield(tui.task), timeout=2)
                terminal.send_text("/exit\r")
                await asyncio.wait_for(app, timeout=2)
            finally:
                finish_turn.set()
                if not app.done():
                    app.cancel()
                    await asyncio.gather(app, return_exceptions=True)
