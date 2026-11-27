"""Deterministic validation, line selection, and matching for workspace text."""

import json
from collections.abc import Iterable


MAX_FILE_BYTES = 4096
MAX_SEARCH_RESULT_BYTES = 4096
MAX_SEARCH_MATCHES = 20
SEARCH_SNIPPET_BYTES = 200
SEARCH_INCOMPLETE = "[Search incomplete. Some files or matches may have been skipped.]"


def validate_line_range(start_line: int | None, end_line: int | None) -> None:
    if (start_line is None) != (end_line is None):
        raise ValueError("Provide both start_line and end_line together.")
    if start_line is not None and end_line is not None:
        if type(start_line) is not int or type(end_line) is not int or not 1 <= start_line <= end_line:
            raise ValueError("Line numbers must be positive integers with start_line at most end_line.")


def select_lines(contents: bytes, start_line: int | None, end_line: int | None) -> str:
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


def _display_path(path: str) -> str:
    if not path.isprintable() or any(char in path for char in ':"\\'):
        return json.dumps(path)
    return path


def search_rows(files: Iterable[tuple[str, bytes]], query: str) -> tuple[list[str], bool]:
    """Return formatted matches and whether the output budget was exhausted."""
    rows: list[str] = []
    result_left = MAX_SEARCH_RESULT_BYTES - len(SEARCH_INCOMPLETE.encode("utf-8"))
    literal = query.encode("utf-8")
    for path, contents in files:
        if b"\0" in contents:
            continue
        try:
            decoded = contents.decode("utf-8")
        except UnicodeDecodeError:
            continue
        display_path = _display_path(path)
        for line_number, line in enumerate(decoded.splitlines(), 1):
            match = line.find(query)
            if match == -1:
                continue
            prefix = f"{display_path}:{line_number}: "
            available = result_left - len(prefix.encode("utf-8")) - 1
            if len(rows) == MAX_SEARCH_MATCHES or available < len(literal):
                return rows, True
            row = prefix + _snippet(line, match, query, literal, available)
            rows.append(row)
            result_left -= len(row.encode("utf-8")) + 1
    return rows, False


def validate_query(query: str) -> None:
    if not query.strip() or query.splitlines() != [query]:
        raise ValueError("Search query must be nonblank, single-line text.")
