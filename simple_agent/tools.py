"""Define application tools here and register them in DEFAULT_TOOLS."""
from datetime import datetime
from pathlib import Path
from stat import S_ISREG
from zoneinfo import ZoneInfo

from strands import tool


MAX_FILE_BYTES = 4096


@tool
def current_time(timezone: str = "UTC") -> str:
    """Return the current time in an IANA timezone, such as America/New_York.

    Args:
        timezone: IANA timezone name.
    """
    return datetime.now(ZoneInfo(timezone)).isoformat()


@tool
def read_file(path: str) -> str:
    """Return the contents of a local UTF-8 text file up to 4 KiB.

    Args:
        path: Absolute path or path relative to the current working directory.
    """
    file_path = Path(path).expanduser()
    if not S_ISREG(file_path.stat().st_mode):
        raise ValueError(f"Expected a regular file at {path!r}.")

    with file_path.open("rb") as file:
        contents = file.read(MAX_FILE_BYTES + 1)
    if len(contents) > MAX_FILE_BYTES:
        raise ValueError(f"File exceeds the {MAX_FILE_BYTES}-byte read limit.")

    return contents.decode("utf-8")


DEFAULT_TOOLS = (current_time, read_file)
