"""Verify conversation and text policy independently of terminal and model I/O."""

import ast
import unittest
from importlib.util import resolve_name
from pathlib import Path

from simple_agent.conversation import Conversation, InvocationError, TextDelta
from simple_agent.preferences import UserPreferences
from simple_agent.tools.workspace_text import search_rows, select_lines
from simple_agent.tui.commands import SlashCommand, matching_commands, parse_slash_command


class ConversationTests(unittest.TestCase):
    def test_failed_turn_restores_history_and_reset_reloads_preferences_and_observer(self):
        class Backend:
            def __init__(self):
                self.history = []

            def apply(self, preferences):
                self.preferences = preferences

            def set_reasoning(self, enabled):
                self.reasoning_enabled = enabled

            def observe(self, emit):
                self.emit = emit

            def checkpoint(self):
                return self.history.copy()

            def restore(self, checkpoint):
                self.history = checkpoint

            def invoke(self, prompt):
                self.history.append(prompt)
                if prompt == "failed":
                    raise InvocationError("Failed")
                self.emit(TextDelta(prompt))

        data = {"agent_name": "Guide"}
        original, fresh = Backend(), Backend()
        backends = iter((original, fresh))
        conversation = Conversation(backends.__next__, UserPreferences(data.copy, data.update))
        events = []
        conversation.observe(events.append)

        self.assertFalse(original.reasoning_enabled)
        conversation.invoke("first")
        conversation.set_reasoning(True)
        self.assertTrue(original.reasoning_enabled)
        with self.assertRaises(InvocationError):
            conversation.invoke("failed")
        self.assertEqual(original.history, ["first"])
        self.assertTrue(conversation.reasoning_enabled)

        conversation.update_preferences("  Scout  ", "")
        self.assertEqual(original.history, ["first"])
        self.assertEqual(original.preferences.name, "Scout")
        self.assertEqual(data["system_prompt"], "")

        conversation.reset()
        conversation.invoke("next")
        self.assertEqual(fresh.preferences, original.preferences)
        self.assertTrue(fresh.reasoning_enabled)
        self.assertEqual(fresh.history, ["next"])
        self.assertEqual(events, [TextDelta("first"), TextDelta("next")])
        self.assertNotIn("reasoning_enabled", data)


class ReasoningCommandTests(unittest.TestCase):
    def test_status_and_explicit_options_parse_in_both_interfaces(self):
        for interactive in (True, False):
            for arg in (None, "on", "off"):
                prompt = f"/reasoning {arg}" if arg else "/reasoning"
                with self.subTest(interactive=interactive, prompt=prompt):
                    self.assertEqual(
                        parse_slash_command(prompt, interactive=interactive),
                        SlashCommand("/reasoning", arg),
                    )
            for arg in ("of", "maybe", "on off"):
                with self.subTest(interactive=interactive, arg=arg):
                    command = parse_slash_command(f"/reasoning {arg}", interactive=interactive)
                    self.assertEqual(
                        command, SlashCommand("/reasoning", error="Usage: /reasoning [on|off]"),
                    )

    def test_completes_the_command_and_its_options(self):
        self.assertIn("/reasoning", matching_commands("/"))
        self.assertEqual(matching_commands("/rea"), ["/reasoning"])
        self.assertEqual(matching_commands("/reasoning "), ["/reasoning on", "/reasoning off"])
        self.assertEqual(matching_commands("/reasoning of"), ["/reasoning off"])


class WorkspaceTextTests(unittest.TestCase):
    def test_ranges_and_search_output_are_independent_of_the_filesystem(self):
        self.assertEqual(select_lines(b"first\r\nsecond\r\n", 2, 4), "second\r\n")
        with self.assertRaisesRegex(ValueError, "Line range exceeds"):
            select_lines(b"x" * 4097, 1, 1)
        rows, truncated = search_rows([("sample.txt", b"one\ntwo")], "two")
        self.assertEqual(rows, ["sample.txt:2: two"])
        self.assertFalse(truncated)


class ArchitectureTests(unittest.TestCase):
    def test_core_and_presentation_dependencies_point_inward(self):
        package = Path(__file__).resolve().parents[1] / "simple_agent"
        core = {
            package / "config.py",
            package / "conversation.py",
            package / "preferences.py",
            package / "tools" / "workspace_text.py",
        }
        adapters = {"agent", "cli", "settings", "strands_backend", "tools"}
        files = sorted(core)
        files.extend(sorted((package / "tui").glob("*.py")))
        for file in files:
            forbidden = adapters | {"create_agent", "strands", "openai"}
            if file in core:
                forbidden |= {"tui", "prompt_toolkit"}
            context = ".".join(("simple_agent", *file.parent.relative_to(package).parts))
            tree = ast.parse(file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    base = resolve_name("." * node.level + (node.module or ""), context)
                    # Keep the package facade's historical pet helper imports available.
                    if file.name == "__init__.py" and base == "simple_agent.settings":
                        self.assertEqual({alias.name for alias in node.names}, {"load_pet", "save_pet"})
                        continue
                    names = [base, *(f"{base}.{alias.name}" for alias in node.names)]
                else:
                    continue
                for name in names:
                    dependency = name.removeprefix("simple_agent.").split(".")[0]
                    self.assertNotIn(dependency, forbidden, f"{file.name}:{node.lineno} imports {name}")
