"""Define application tools here and register them in DEFAULT_TOOLS."""
import json
import os
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import datetime
from io import BufferedReader
from pathlib import Path
from stat import S_ISREG
from zoneinfo import ZoneInfo

from strands import tool

MAX_FILE_BYTES = 4096
MAX_CANDIDATE_FILE_BYTES = 1024 * 1024
MAX_SEARCH_RESULT_BYTES = 4096
MAX_SEARCH_MATCHES = 20
MAX_SEARCH_ENTRIES = 10_000
MAX_SEARCH_READ_BYTES = 32 * 1024 * 1024
MAX_SEARCH_DEPTH = 32
SEARCH_SNIPPET_BYTES = 200
SEARCH_INCOMPLETE = "[Search incomplete. Some files or matches may have been skipped.]"
SEARCH_SKIP_NAMES = frozenset({".venv", "__pycache__", "node_modules"})
ALLOWED_ENV_FILES = frozenset({".env.example", ".env.sample", ".env.template"})
DIRECTORY_FLAGS = os.O_DIRECTORY | os.O_NOFOLLOW
DIRECTORY_READ_FLAGS = DIRECTORY_FLAGS | os.O_RDONLY
# A known path only requires search permission on its parent directories.
DIRECTORY_LOOKUP_FLAGS = DIRECTORY_FLAGS | getattr(os, "O_PATH", getattr(os, "O_SEARCH", os.O_RDONLY))
FILE_FLAGS = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW


def _is_sensitive_path(rel_parts: tuple[str, ...]) -> bool:
    if ".git" in rel_parts:
        return True
    name = rel_parts[-1]
    return name == ".env" or (name.startswith(".env.") and name not in ALLOWED_ENV_FILES)


@contextmanager
def _open_regular_file(
    parent_fd: int, name: str, path: str
) -> Iterator[tuple[BufferedReader, os.stat_result]]:
    fd = os.open(name, FILE_FLAGS, dir_fd=parent_fd)
    try:
        info = os.fstat(fd)
        if not S_ISREG(info.st_mode):
            raise ValueError(f"Expected a regular file at {path!r}.")
        with os.fdopen(fd, "rb") as file:
            fd = -1
            yield file, info
    finally:
        if fd >= 0:
            os.close(fd)


@contextmanager
def _open_workspace_file(rel_parts: tuple[str, ...], path: str) -> Iterator[BufferedReader]:
    parent_fd = os.open(".", DIRECTORY_LOOKUP_FLAGS)
    try:
        for name in rel_parts[:-1]:
            child_fd = os.open(name, DIRECTORY_LOOKUP_FLAGS, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = child_fd
        name = rel_parts[-1]
        info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not S_ISREG(info.st_mode):
            raise ValueError(f"Expected a regular file at {path!r}.")
        with _open_regular_file(parent_fd, name, path) as (file, _):
            yield file
    finally:
        os.close(parent_fd)


@tool
def current_time(timezone: str = "UTC") -> str:
    """Return the current time in an IANA timezone, such as America/New_York.

    Args:
        timezone: IANA timezone name.
    """
    return datetime.now(ZoneInfo(timezone)).isoformat()


@tool
def read_file(path: str, start_line: int | None = None, end_line: int | None = None) -> str:
    """Read a local UTF-8 text file or inclusive line range in the working directory.

    The return value is raw text up to 4 KiB. Line ranges support files up to 1 MiB.

    Args:
        path: Path inside the current working directory (relative or absolute).
        start_line: First line to include, starting at 1. Provide both line numbers or neither.
        end_line: Last line to include. Values past the end of the file are clipped.
    """
    if (start_line is None) != (end_line is None):
        raise ValueError("Provide both start_line and end_line together.")
    if start_line is not None and end_line is not None:
        if type(start_line) is not int or type(end_line) is not int or not 1 <= start_line <= end_line:
            raise ValueError("Line numbers must be positive integers with start_line at most end_line.")

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

    limit = MAX_FILE_BYTES if start_line is None else MAX_CANDIDATE_FILE_BYTES
    with _open_workspace_file(rel_parts, path) as file:
        contents = file.read(limit + 1)
    if len(contents) > limit:
        raise ValueError(f"File exceeds the {limit}-byte read limit.")

    decoded = contents.decode("utf-8")
    if start_line is None:
        return decoded
    selected = "".join(decoded.splitlines(keepends=True)[start_line - 1 : end_line])
    if len(selected.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError(f"Line range exceeds the {MAX_FILE_BYTES}-byte read limit.")
    return selected


def _snippet(line: str, match: int, query: str, literal: bytes, available: int) -> str:
    limit = min(available, max(SEARCH_SNIPPET_BYTES, len(literal)))
    context = limit - len(literal)
    match_end = match + len(query)
    left = line[max(0, match - context) : match].encode("utf-8")
    right = line[match_end : match_end + context].encode("utf-8")
    left_limit = min(len(left), max(context // 2, context - len(right)))
    right_limit = context - left_limit
    left = left[len(left) - left_limit :]
    right = right[:right_limit]
    return (left + literal + right).decode("utf-8", errors="ignore")


@tool
def search_text(query: str) -> str:
    """Find case-sensitive literal text in UTF-8 files under the working directory.

    Returns up to 20 matches as relative path, line number, and a snippet.
    An incomplete notice indicates a scan or output limit or files that could not be read.

    Args:
        query: Nonblank, single-line text to find. Special characters are matched literally.
    """
    if not query.strip() or query.splitlines() != [query]:
        raise ValueError("Search query must be nonblank, single-line text.")

    incomplete = False
    entries_left = MAX_SEARCH_ENTRIES

    def candidates(directory_fd: int, path: str, depth: int) -> Iterator[tuple[int, str, str]]:
        nonlocal incomplete, entries_left
        children = []
        with os.scandir(directory_fd) as entries:
            for entry in entries:
                if entries_left == 0:
                    incomplete = True
                    return
                entries_left -= 1
                if entry.name in SEARCH_SKIP_NAMES or _is_sensitive_path((entry.name,)):
                    continue
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                    if is_dir or entry.is_file(follow_symlinks=False):
                        children.append((entry.name + "/" if is_dir else entry.name, is_dir))
                except OSError:
                    incomplete = True

        for name, is_dir in sorted(children):
            relative = path + name
            if not is_dir:
                yield directory_fd, name, relative
                continue
            if depth == MAX_SEARCH_DEPTH or entries_left == 0:
                incomplete = True
                continue
            try:
                child_fd = os.open(name[:-1], DIRECTORY_READ_FLAGS, dir_fd=directory_fd)
                try:
                    yield from candidates(child_fd, relative, depth + 1)
                finally:
                    os.close(child_fd)
            except OSError:
                incomplete = True

    rows = []
    result_left = MAX_SEARCH_RESULT_BYTES - len(SEARCH_INCOMPLETE.encode("utf-8"))
    read_left = MAX_SEARCH_READ_BYTES
    literal = query.encode("utf-8")
    try:
        root_fd = os.open(".", DIRECTORY_READ_FLAGS)
    except OSError:
        return SEARCH_INCOMPLETE
    try:
        with closing(candidates(root_fd, "", 0)) as files:
            for parent_fd, name, path in files:
                try:
                    with _open_regular_file(parent_fd, name, path) as (file, info):
                        if info.st_size > MAX_CANDIDATE_FILE_BYTES:
                            incomplete = True
                            continue
                        limit = min(MAX_CANDIDATE_FILE_BYTES, read_left - 1)
                        if info.st_size > limit:
                            incomplete = True
                            break
                        contents = file.read(limit + 1)
                except (OSError, ValueError):
                    incomplete = True
                    continue

                read_left -= len(contents)
                if len(contents) > limit:
                    incomplete = True
                    if read_left == 0:
                        break
                    continue
                if b"\0" in contents:
                    continue
                try:
                    decoded = contents.decode("utf-8")
                except UnicodeDecodeError:
                    continue

                display_path = path
                if not path.isprintable() or any(char in path for char in ':"\\'):
                    display_path = json.dumps(path)
                for line_number, line in enumerate(decoded.splitlines(), 1):
                    match = line.find(query)
                    if match == -1:
                        continue
                    prefix = f"{display_path}:{line_number}: "
                    available = result_left - len(prefix.encode("utf-8")) - 1
                    if len(rows) == MAX_SEARCH_MATCHES or available < len(literal):
                        return "\n".join([*rows, SEARCH_INCOMPLETE])
                    row = prefix + _snippet(line, match, query, literal, available)
                    rows.append(row)
                    result_left -= len(row.encode("utf-8")) + 1
    except OSError:
        incomplete = True
    finally:
        os.close(root_fd)

    if incomplete:
        rows.append(SEARCH_INCOMPLETE)
    return "\n".join(rows) if rows else "No matches."


DEFAULT_TOOLS = (current_time, read_file, search_text)
