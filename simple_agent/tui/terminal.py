"""Handle terminal capability checks and shared stdout writes."""
import os
import sys
from collections.abc import Callable


def interactive_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty() and os.getenv("TERM") != "dumb"


def use_color() -> bool:
    return sys.stdout.isatty() and not os.getenv("NO_COLOR") and os.getenv("TERM") != "dumb"


def use_true_color() -> bool:
    return os.getenv("COLORTERM", "").lower() in {"truecolor", "24bit"}


def write_stdout(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def write_rows(lines: list[str], write: Callable[[str], None] = write_stdout) -> None:
    write("".join(line + "\n" for line in lines))
