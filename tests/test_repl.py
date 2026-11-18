import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from simple_agent.repl import Turn


class TurnTests(unittest.TestCase):
    def test_wraps_streamed_words_and_indents_explicit_lines(self):
        output = io.StringIO()
        with redirect_stdout(output), patch.dict(os.environ, {"COLUMNS": "21"}):
            turn = Turn("Gemma>", "1;32")
            turn.write("One two thr")
            turn.write("ee four\n\n  In")
            turn.write("dented line")
            turn.finish()

        self.assertEqual(
            output.getvalue(),
            "Gemma> One two three\n       four\n\n         Indented\n       line\n",
        )

    def test_tool_lines_stay_inside_the_agent_turn(self):
        output = io.StringIO()
        with redirect_stdout(output), patch.dict(os.environ, {"COLUMNS": "80"}):
            turn = Turn("Gemma>", "1;32")
            turn.write("Checking")
            turn.tool("Tool #1:", "current_time")
            turn.write("Done.\n")
            turn.finish()

        self.assertEqual(
            output.getvalue(),
            "Gemma> Checking\n       Tool #1: current_time\n       Done.\n",
        )
