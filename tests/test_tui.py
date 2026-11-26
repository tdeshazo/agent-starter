import asyncio
import unittest
from types import SimpleNamespace

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from simple_agent.tui import AgentTui, Transcript


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


class AgentTuiTests(unittest.IsolatedAsyncioTestCase):
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
        with create_pipe_input() as terminal:
            tui = AgentTui(lambda: agent, input=terminal, output=DummyOutput(), color=False)
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
