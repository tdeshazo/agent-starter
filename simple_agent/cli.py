"""Command-line interface for the local Gemma agent."""
import argparse
from collections.abc import Callable, Sequence
import os
from pathlib import Path
import shutil
import sys

from .agent import create_agent
from .settings import apply_agent_settings
from .tui import PET_NAMES, AgentTui, interactive_terminal, run_plain, save_pet
from .tui.rendering import error_cell
from .tui.session import conversation_turn
from .tui.transcript import INTERRUPTED, format_invocation_error


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
    if args.pet:
        try:
            save_pet(args.pet, config_path)
        except OSError as error:
            _write_stderr_error(f"Could not save pet preference: {error.strerror or error}")
            return 1
    if args.prompt:
        agent = agent_factory()
        apply_agent_settings(agent, config_path)
        try:
            with conversation_turn(getattr(agent, "messages", [])):
                agent(args.prompt)
        except KeyboardInterrupt:
            sys.stderr.write("\n")
            _write_stderr_error(INTERRUPTED)
            return 130
        except Exception as error:
            _write_stderr_error(format_invocation_error(error))
            return 1
        print()
        return 0
    if interactive_terminal():
        AgentTui(agent_factory, config_path=config_path).run()
    else:
        run_plain(agent_factory, config_path=config_path)
    return 0


def main(argv: Sequence[str] | None = None) -> None:
    code = run_cli(argv)
    if code:
        raise SystemExit(code)
