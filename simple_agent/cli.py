"""Command-line interface for the local Gemma agent."""
import argparse
import os
import shutil
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from .agent import create_agent, create_conversation
from .conversation import InvocationError
from .preferences import PET_NAMES
from .settings import open_preferences
from .tui import AgentTui, interactive_terminal, run_plain
from .tui.rendering import error_cell
from .tui.transcript import INTERRUPTED


def _stderr_color() -> bool:
    return sys.stderr.isatty() and not os.getenv("NO_COLOR") and os.getenv("TERM") != "dumb"


def _write_stderr_error(message: str) -> None:
    width = shutil.get_terminal_size().columns
    rows = error_cell(message, width, color=_stderr_color())
    sys.stderr.write("".join(row + "\n" for row in rows))
    sys.stderr.flush()


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    agent_factory: Callable[[], object] = create_agent,
    config_path: Path | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", nargs="?", help="Omit for an interactive conversation")
    parser.add_argument(
        "--pet",
        choices=PET_NAMES,
        help=f"Select and save the header pet ({', '.join(PET_NAMES)})",
    )
    args = parser.parse_args(argv)
    preferences = open_preferences(config_path)
    if args.pet:
        try:
            preferences.select_pet(args.pet)
        except OSError as error:
            _write_stderr_error(f"Could not save pet preference: {error.strerror or error}")
            return 1
    try:
        conversation = create_conversation(agent_factory, preferences)
        if args.prompt:
            conversation.invoke(args.prompt)
            print()
        elif interactive_terminal():
            AgentTui(conversation, preferences).run()
        else:
            run_plain(conversation, preferences)
    except KeyboardInterrupt:
        sys.stderr.write("\n")
        _write_stderr_error(INTERRUPTED)
        return 130
    except InvocationError as error:
        _write_stderr_error(str(error))
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> None:
    code = run_cli(argv)
    if code:
        raise SystemExit(code)
