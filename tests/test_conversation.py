"""Verify conversation and text policy independently of terminal and model I/O."""

import ast
import unittest
from importlib.util import resolve_name
from pathlib import Path

from simple_agent.conversation import Conversation, InvocationError, TextDelta
from simple_agent.preferences import UserPreferences
from simple_agent.workspace_text import search_rows, select_lines


class ConversationTests(unittest.TestCase):
    def test_failed_turn_restores_history_and_reset_reloads_preferences_and_observer(self):
        class Backend:
            def __init__(self):
                self.history = []

            def apply(self, preferences):
                self.preferences = preferences

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

        conversation.invoke("first")
        with self.assertRaises(InvocationError):
            conversation.invoke("failed")
        self.assertEqual(original.history, ["first"])

        conversation.update_preferences("  Scout  ", "")
        self.assertEqual(original.history, ["first"])
        self.assertEqual(original.preferences.name, "Scout")
        self.assertEqual(data["system_prompt"], "")

        conversation.reset()
        conversation.invoke("next")
        self.assertEqual(fresh.preferences, original.preferences)
        self.assertEqual(fresh.history, ["next"])
        self.assertEqual(events, [TextDelta("first"), TextDelta("next")])


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
        core = {"config", "conversation", "preferences", "workspace_text"}
        adapters = {"agent", "cli", "settings", "strands_backend", "tools", "workspace_files"}
        files = [package / f"{name}.py" for name in sorted(core)]
        files.extend(sorted((package / "tui").glob("*.py")))
        for file in files:
            forbidden = adapters | {"create_agent", "strands", "openai"}
            if file.parent == package:
                forbidden |= {"tui", "prompt_toolkit"}
            context = "simple_agent.tui" if file.parent.name == "tui" else "simple_agent"
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
