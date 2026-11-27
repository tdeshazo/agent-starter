"""Expose bounded workspace access as Strands tools."""

from contextlib import closing

from strands import tool

from .workspace_files import MAX_CANDIDATE_FILE_BYTES, WorkspaceScan, read_workspace_bytes
from .workspace_text import (
    MAX_FILE_BYTES,
    SEARCH_INCOMPLETE,
    search_rows,
    select_lines,
    validate_line_range,
    validate_query,
)


@tool
def read_file(path: str, start_line: int | None = None, end_line: int | None = None) -> str:
    """Read a local UTF-8 text file or inclusive line range in the working directory.

    The return value is raw text up to 4 KiB. Line ranges support files up to 1 MiB.

    Args:
        path: Path inside the current working directory (relative or absolute).
        start_line: First line to include, starting at 1. Provide both line numbers or neither.
        end_line: Last line to include. Values past the end of the file are clipped.
    """
    validate_line_range(start_line, end_line)
    limit = MAX_FILE_BYTES if start_line is None else MAX_CANDIDATE_FILE_BYTES
    return select_lines(read_workspace_bytes(path, limit), start_line, end_line)


@tool
def search_text(query: str) -> str:
    """Find case-sensitive literal text in UTF-8 files under the working directory.

    Returns up to 20 matches as relative path, line number, and a snippet.
    An incomplete notice indicates a scan or output limit or files that could not be read.

    Args:
        query: Nonblank, single-line text to find. Special characters are matched literally.
    """
    validate_query(query)
    scan = WorkspaceScan()
    with closing(scan.files()) as files:
        rows, truncated = search_rows(files, query)
    if scan.incomplete or truncated:
        rows.append(SEARCH_INCOMPLETE)
    return "\n".join(rows) if rows else "No matches."
