import asyncio
import io
import os
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from prompt_toolkit.input import create_pipe_input

from simple_agent.repl import ReplOutput, Turn


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


class ReplOutputTests(unittest.TestCase):
    def test_escape_stops_stream_and_restores_history(self):
        previous_turn = {"role": "assistant", "content": [{"text": "Earlier reply"}]}
        output = io.StringIO()
        with create_pipe_input() as terminal, redirect_stdout(output):
            async def invoke(prompt):
                if prompt == "follow-up":
                    self.assertEqual(agent.messages, [previous_turn])
                    agent.callback_handler(data="Next reply")
                    return
                agent.messages.append({"role": "user", "content": [{"text": prompt}]})
                agent.callback_handler(data="Partial reply")
                terminal.send_bytes(b"\x1b")
                await asyncio.wait_for(asyncio.Event().wait(), timeout=2)

            agent = SimpleNamespace(
                model=SimpleNamespace(get_config=lambda: {"model_id": "gemma-4-e4b"}),
                messages=[previous_turn],
                invoke_async=invoke,
            )
            repl = ReplOutput(agent)
            repl.respond(agent, "interrupted", terminal)
            repl.respond(agent, "follow-up", terminal)

        self.assertEqual(
            output.getvalue(),
            "Gemma> Partial reply\n[Response stopped]\nGemma> Next reply\n",
        )
