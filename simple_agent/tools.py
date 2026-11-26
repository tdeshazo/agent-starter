"""Define application tools here and register them in DEFAULT_TOOLS."""
from datetime import datetime
import os
from pathlib import Path
from stat import S_ISREG
from zoneinfo import ZoneInfo

from strands import tool


MAX_FILE_BYTES = 4096
ALLOWED_ENV_FILES = frozenset({".env.example", ".env.sample", ".env.template"})


def _is_sensitive_path(rel_parts: tuple[str, ...]) -> bool:
    if ".git" in rel_parts:
        return True
    name = rel_parts[-1]
    return name == ".env" or (name.startswith(".env.") and name not in ALLOWED_ENV_FILES)


@tool
def current_time(timezone: str = "UTC") -> str:
    """Return the current time in an IANA timezone, such as America/New_York.

    Args:
        timezone: IANA timezone name.
    """
    return datetime.now(ZoneInfo(timezone)).isoformat()


@tool
def read_file(path: str) -> str:
    """Return the contents of a local UTF-8 text file in the working directory up to 4 KiB.

    Args:
        path: Path inside the current working directory (relative or absolute).
    """
    root = Path.cwd().resolve()
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"Path {path!r} is outside the working directory.")
    rel_parts = resolved.relative_to(root).parts
    if not rel_parts:
        raise ValueError(f"Expected a regular file at {path!r}.")
    if _is_sensitive_path(rel_parts):
        raise ValueError(f"Reading sensitive file {path!r} is not allowed.")

    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(resolved, flags)
    try:
        if not S_ISREG(os.fstat(fd).st_mode):
            raise ValueError(f"Expected a regular file at {path!r}.")
        with os.fdopen(fd, "rb") as file:
            fd = -1
            contents = file.read(MAX_FILE_BYTES + 1)
    finally:
        if fd >= 0:
            os.close(fd)

    if len(contents) > MAX_FILE_BYTES:
        raise ValueError(f"File exceeds the {MAX_FILE_BYTES}-byte read limit.")

    return contents.decode("utf-8")


DEFAULT_TOOLS = (current_time, read_file)
