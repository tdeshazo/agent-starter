"""Run the line-oriented terminal interface for pipes and dumb terminals."""
import shutil
import time
from collections.abc import Callable

from .commands import command_output
from .session import conversation_turn, session_info
from .terminal import use_color, write_rows
from .transcript import Transcript


def run_plain(agent_factory: Callable[[], object], agent=None, read: Callable[[], str] = input) -> None:
    """Line-oriented fallback for pipes and dumb terminals."""
    color = use_color()
    transcript = Transcript(
        write_rows,
        lambda: shutil.get_terminal_size().columns,
        color,
    )
    agent = agent if agent is not None else agent_factory()
    agent.callback_handler = transcript
    transcript.header(**session_info(agent))
    while True:
        try:
            entered = read()
        except (EOFError, KeyboardInterrupt):
            break
        prompt = entered.strip()
        if not prompt:
            continue
        if prompt == "/exit":
            break
        if prompt == "/clear":
            agent = agent_factory()
            agent.callback_handler = transcript
            transcript.info("Started a new conversation.")
            continue
        if result := command_output(prompt, agent):
            transcript.info(result)
            continue
        transcript.user(entered)
        started = time.monotonic()
        try:
            with conversation_turn(agent.messages):
                agent(prompt)
        except KeyboardInterrupt:
            transcript.end_turn(time.monotonic() - started, stopped=True)
            break
        except Exception as error:
            transcript.invocation_failed(error)
        transcript.end_turn(time.monotonic() - started)
