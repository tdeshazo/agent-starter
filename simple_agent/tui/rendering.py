"""Render terminal headers, transcript cells, and streamed text."""
import json
import re
import unicodedata

from prompt_toolkit.utils import get_cwidth

from ..conversation import ToolResult
from ..preferences import DEFAULT_AGENT_NAME, DEFAULT_PET
from .markdown import (
    BOLD,
    BOLD_RED,
    BOLD_RED_LIGHT,
    CYAN,
    DIM,
    ITALIC,
    STRIKE,
    UNDERLINE,
    WORD,
    bold_markdown_style,
    can_be_table_delimiter_prefix,
    fence_transition,
    is_table_body_row,
    is_table_header_candidate,
    parse_table_alignments,
    render_markdown_line,
    render_table,
    sgr,
    split_table_cells,
    split_width,
    wrap_ranges,
)
from .pets import PET_GAP, pet_rows, pet_width


TOOL_RESULT_LINES = 3
MAX_ESCAPE_BUFFER = 256

ITALIC_DIM = "2;3"
BOLD_CYAN = "1;36"
USER_TEXT = "38;5;152"
USER_TEXT_LIGHT = "38;5;23"
RED = "31"

__all__ = [
    "BOLD",
    "BOLD_CYAN",
    "BOLD_RED",
    "BOLD_RED_LIGHT",
    "CYAN",
    "DIM",
    "ITALIC",
    "ITALIC_DIM",
    "RED",
    "STRIKE",
    "StreamCell",
    "TOKEN_USAGE_FIELDS",
    "UNDERLINE",
    "USER_TEXT",
    "USER_TEXT_LIGHT",
    "bold_markdown_style",
    "error_cell",
    "format_elapsed",
    "format_tokens",
    "header_cell",
    "info_cell",
    "sanitize_text",
    "separator_cell",
    "session_box",
    "sgr",
    "shimmer",
    "tool_call_rows",
    "tool_result_rows",
    "truncate",
    "usage_cell",
    "user_cell",
    "user_text_style",
    "wrap",
]

ANSI_ESCAPE = re.compile(
    r"\x1b(?:"
    r"\[[0-?]*[ -/]*[@-~]"
    r"|\][^\x07\x1b]*(?:\x07|\x1b\\)"
    r"|[P^_][^\x1b]*\x1b\\"
    r"|[@-Z\\-_]"
    r")"
    r"|\x9b[0-?]*[ -/]*[@-~]"
)
INCOMPLETE_ANSI = re.compile(
    r"(?:\x1b(?:\[[0-?]*[ -/]*|\][^\x07\x1b]*|[P^_][^\x1b]*)?|\x9b[0-?]*[ -/]*)\Z"
)
TOKEN_USAGE_FIELDS = (("input", "in"), ("cache_read", "cached"), ("output", "out"))


def sanitize_text(text: str, *, multiline: bool = True) -> str:
    """Strip terminal escape sequences and unsafe control characters from untrusted text."""
    if not text:
        return ""
    cleaned = text.replace("\r\n", "\n")
    if "\x1b" in cleaned or "\x9b" in cleaned:
        cleaned = ANSI_ESCAPE.sub("", cleaned)
    out: list[str] = []
    for char in cleaned:
        if char == "\n":
            out.append("\n" if multiline else " ")
        elif char == "\t":
            out.append("\t" if multiline else " ")
        else:
            category = unicodedata.category(char)
            if category in {"Zl", "Zp"}:
                out.append("\n" if multiline else " ")
            elif category != "Cc":
                out.append(char)
    return "".join(out)


_split_width = split_width


def wrap(text: str, width: int) -> list[str]:
    """Word-wrap one logical line by display width.

    Leading indentation is kept, words longer than a row start a new row and are
    broken there. Rows other than the last never change when text is appended,
    which lets streamed rows be committed to the transcript as soon as they fill.
    """
    expanded = text.expandtabs(4)
    return [expanded[start:end] for start, end in wrap_ranges(expanded, width)]


def truncate(text: str, width: int) -> str:
    """Shorten text to width columns, ending with an ellipsis when cut."""
    if get_cwidth(text) <= width:
        return text
    head, _ = _split_width(text, max(width - 1, 0))
    return head + "…"


def _prefixed(rows: list[str], first: str, rest: str) -> list[str]:
    return [(first if index == 0 else rest) + row for index, row in enumerate(rows)]


def format_elapsed(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes}m {seconds:02d}s"


def shimmer(text: str, now: float, color: bool = True) -> str:
    """Return text with a bright band sweeping across it."""
    if not color:
        return text
    period = len(text) + 8
    center = (now * 14) % period - 4
    out = []
    for index, char in enumerate(text):
        distance = abs(index - center)
        code = BOLD if distance < 1.5 else ("" if distance < 3 else DIM)
        out.append(sgr(char, code))
    return "".join(out)


def header_cell(
    model: str | None,
    endpoint: str | None,
    directory: str,
    app_version: str | None,
    width: int,
    color: bool = True,
    *,
    true_color: bool = False,
    pet: str = DEFAULT_PET,
    agent_name: str = DEFAULT_AGENT_NAME,
) -> list[str]:
    """Render the session box shown at startup, with the pet beside it when it fits."""
    art_width = pet_width(pet)
    side_width = art_width + PET_GAP
    if width - side_width >= 40:
        box = session_box(model, endpoint, directory, app_version, width - side_width, color, agent_name=agent_name)
        art = pet_rows(pet, color, true_color=true_color)
        height = max(len(box), len(art))
        art += [" " * art_width] * (height - len(art))
        box += [""] * (height - len(box))
        return [(pet_line + " " * PET_GAP + line).rstrip() for pet_line, line in zip(art, box)]
    return session_box(model, endpoint, directory, app_version, width, color, agent_name=agent_name)


def session_box(
    model: str | None,
    endpoint: str | None,
    directory: str,
    app_version: str | None,
    width: int,
    color: bool = True,
    *,
    agent_name: str = DEFAULT_AGENT_NAME,
) -> list[str]:
    """Render the bordered box listing the session's model, endpoint and directory."""
    safe_name = sanitize_text(agent_name, multiline=False) or DEFAULT_AGENT_NAME
    safe_version = sanitize_text(app_version or "", multiline=False)
    title = safe_name + (f" (v{safe_version})" if safe_version else "")
    fields = [
        (name, cleaned)
        for name, value in (
            ("model:", model),
            ("endpoint:", endpoint),
            ("directory:", directory),
        )
        if value and (cleaned := sanitize_text(value, multiline=False))
    ]
    label_width = max((len(name) for name, _ in fields), default=0) + 1
    plain = [title] + ([""] + [name.ljust(label_width) + value for name, value in fields] if fields else [])
    inner = min(max(get_cwidth(line) for line in plain), max(width - 4, 10))
    plain = [truncate(line, inner) for line in plain]

    def styled_line(index: int, line: str) -> str:
        if index == 0:
            split = min(len(safe_name), len(line))
            return sgr(line[:split], BOLD, color) + sgr(line[split:], DIM, color)
        if line:
            return sgr(line[:label_width], DIM, color) + line[label_width:]
        return line

    def border(text: str) -> str:
        return sgr(text, DIM, color)

    lines = [border("╭" + "─" * (inner + 2) + "╮")]
    for index, line in enumerate(plain):
        padding = " " * (inner - get_cwidth(line))
        lines.append(border("│") + " " + styled_line(index, line) + padding + " " + border("│"))
    lines.append(border("╰" + "─" * (inner + 2) + "╯"))
    return lines


def user_text_style(light: bool = False) -> str:
    return USER_TEXT_LIGHT if light else USER_TEXT


def user_cell(text: str, width: int, color: bool = True, *, light: bool = False) -> list[str]:
    clean = sanitize_text(text)
    style = user_text_style(light)
    rows = [
        sgr(row, style, color)
        for line in clean.strip("\n").split("\n")
        for row in wrap(line, width - 2)
    ]
    return _prefixed(rows, sgr("›", BOLD_CYAN, color) + " ", "  ")


def tool_call_rows(name: str, tool_input, width: int, color: bool = True, verb: str = "Called") -> list[str]:
    try:
        arguments = json.dumps(tool_input, ensure_ascii=False)
    except (TypeError, ValueError):
        arguments = str(tool_input)
    safe_name = sanitize_text(str(name), multiline=False)
    safe_arguments = sanitize_text(arguments, multiline=False)
    rows = wrap(f"{verb} {safe_name}({safe_arguments})", width - 2)
    rows[0] = sgr(verb, BOLD, color) + rows[0][len(verb):]
    return _prefixed(rows, "• ", "  ")


def tool_result_rows(result: ToolResult, width: int, color: bool = True) -> list[str]:
    text = "\n".join(sanitize_text(part) for part in result.parts)
    lines = [line for line in text.splitlines() if line.strip()] or ["(no output)"]
    shown = lines[:TOOL_RESULT_LINES]
    hidden = len(lines) - len(shown)
    if hidden:
        shown.append(f"… +{hidden} lines")
    style = RED if result.failed else DIM
    rows = [truncate(line, width - 4) for line in shown]
    return [
        "  " + sgr("└ " if index == 0 else "  ", DIM, color) + sgr(row, style, color)
        for index, row in enumerate(rows)
    ]


def error_cell(message: str, width: int, color: bool = True) -> list[str]:
    clean = sanitize_text(message)
    rows = [sgr(row, RED, color) for line in clean.split("\n") for row in wrap(line, width - 2)]
    return _prefixed(
        rows,
        sgr("■", RED, color) + " ",
        "  ",
    )


def info_cell(message: str, width: int, color: bool = True) -> list[str]:
    clean = sanitize_text(message)
    rows = [sgr(row, DIM, color) for line in clean.split("\n") for row in wrap(line, width - 2)]
    return _prefixed(rows, sgr("•", DIM, color) + " ", "  ")


def separator_cell(elapsed: float, width: int, color: bool = True) -> list[str]:
    label = f"─ Worked for {format_elapsed(elapsed)} "
    return [sgr(label + "─" * max(width - get_cwidth(label), 0), DIM, color)]


class StreamCell:
    """Wrap streamed text, committing rows once later text cannot change them."""

    def __init__(
        self,
        width: int,
        bullet: str,
        style: str = "",
        color: bool = True,
        markdown: bool = False,
        *,
        light: bool = False,
    ):
        self.width = max(width - 2, 1)
        self.bullet = bullet
        self.style = style
        self.color = color
        self.markdown = markdown
        self.light = light
        self.line = ""
        self.committed = 0
        self.started = False
        self.blank_rows = 0
        self.fence: tuple[str, int] | None = None
        self._list_indents: list[tuple[int, int]] = []
        self._quote_list_indents: list[tuple[int, int]] = []
        self._table_lines: list[str] = []
        self._pending_escape = ""

    @property
    def in_fence(self) -> bool:
        return self.fence is not None

    def _prefix(self, *, suppress_bullet: bool = False) -> str:
        if self.started or (self.markdown and suppress_bullet):
            return "  "
        return self.bullet + " "

    def _rows_plain(self, rows: list[str]) -> list[str]:
        out: list[str] = []
        for row in rows:
            if not row.strip():
                if self.started:
                    self.blank_rows += 1
                continue
            out.extend([""] * self.blank_rows)
            self.blank_rows = 0
            out.append(self._prefix() + sgr(row, self.style, self.color))
            self.started = True
        return out

    def _emit_rendered(self, rendered_rows: list[str], *, suppress_bullet: bool = False) -> list[str]:
        out: list[str] = []
        for row in rendered_rows:
            if not row.strip():
                if self.started:
                    self.blank_rows += 1
                continue
            out.extend([""] * self.blank_rows)
            self.blank_rows = 0
            out.append(self._prefix(suppress_bullet=suppress_bullet) + row)
            self.started = True
        return out

    def _flush_table(self) -> list[str]:
        if not self._table_lines:
            return []
        lines = self._table_lines
        self._table_lines = []
        if len(lines) == 1:
            return self._commit_non_table_line(lines[0])
        self._list_indents.clear()
        self._quote_list_indents.clear()
        return self._emit_rendered(
            render_table(lines, self.width, self.color, light=self.light),
            suppress_bullet=True,
        )

    def _commit_non_table_line(self, line: str) -> list[str]:
        is_fence, next_fence = fence_transition(line, self.fence)
        if is_fence:
            self.fence = next_fence
            self._quote_list_indents.clear()
            rows = [sgr(row, DIM, self.color) for row in wrap(line, self.width)]
            return self._emit_rendered(rows)
        if self.fence is not None:
            return self._emit_rendered(wrap(line, self.width))
        if not line.strip():
            self._quote_list_indents.clear()
            if self.started:
                self.blank_rows += 1
            return []
        rendered, suppress = render_markdown_line(
            line, self.width, self._list_indents, self._quote_list_indents, self.color, light=self.light,
        )
        return self._emit_rendered(rendered, suppress_bullet=suppress)

    def _commit_markdown_line(self, line: str) -> list[str]:
        out: list[str] = []
        if self.fence is not None:
            return self._commit_non_table_line(line)
        if len(self._table_lines) == 1:
            header_cells, _ = split_table_cells(self._table_lines[0])
            if parse_table_alignments(line, len(header_cells)) is not None:
                self._table_lines.append(line)
                return out
            out.extend(self._flush_table())
        elif len(self._table_lines) >= 2:
            if is_table_body_row(line):
                self._table_lines.append(line)
                return out
            out.extend(self._flush_table())

        if is_table_header_candidate(line):
            self._table_lines.append(line)
            return out
        out.extend(self._commit_non_table_line(line))
        return out

    def push(self, chunk: str) -> list[str]:
        """Add streamed text and return rows that are now final."""
        raw = self._pending_escape + chunk
        self._pending_escape = ""
        if "\x1b" in raw or "\x9b" in raw:
            match = INCOMPLETE_ANSI.search(raw)
            if match and len(raw) - match.start() <= MAX_ESCAPE_BUFFER:
                self._pending_escape = raw[match.start() :]
                raw = raw[: match.start()]
        *complete, self.line = (self.line + sanitize_text(raw)).split("\n")
        rows: list[str] = []
        if self.markdown:
            for line in complete:
                rows.extend(self._commit_markdown_line(line))
            if (
                len(self._table_lines) == 1
                and self.line
                and not can_be_table_delimiter_prefix(self.line)
            ):
                rows.extend(self._flush_table())
            return rows

        for line in complete:
            rows.extend(self._rows_plain(wrap(line, self.width)[self.committed :]))
            self.committed = 0
        current = wrap(self.line, self.width)
        rows.extend(self._rows_plain(current[self.committed : len(current) - 1]))
        self.committed = max(self.committed, len(current) - 1)
        return rows

    def tail(self) -> list[str]:
        """Return uncommitted rows as they would appear if committed now."""
        if not self.markdown:
            row = wrap(self.line, self.width)[-1]
            if not row.strip():
                return []
            blanks = [""] * self.blank_rows if self.started else []
            return blanks + [self._prefix() + sgr(row, self.style, self.color)]

        started = self.started
        blank_rows = self.blank_rows
        fence = self.fence
        list_indents = self._list_indents.copy()
        quote_indents = self._quote_list_indents.copy()

        def preview_emit(rendered_rows: list[str], *, suppress_bullet: bool = False) -> list[str]:
            nonlocal started, blank_rows
            out: list[str] = []
            for row in rendered_rows:
                if not row.strip():
                    if started:
                        blank_rows += 1
                    continue
                if started:
                    out.extend([""] * blank_rows)
                blank_rows = 0
                prefix = "  " if (started or suppress_bullet) else self.bullet + " "
                out.append(prefix + row)
                started = True
            return out

        def preview_non_table(line: str) -> list[str]:
            if not line.strip():
                return []
            is_f, _ = fence_transition(line, fence)
            if is_f:
                return preview_emit([sgr(r, DIM, self.color) for r in wrap(line, self.width)])
            if fence is not None:
                return preview_emit(wrap(line, self.width))
            rendered, suppress = render_markdown_line(
                line, self.width, list_indents, quote_indents, self.color, light=self.light,
            )
            return preview_emit(rendered, suppress_bullet=suppress)

        if len(self._table_lines) >= 2:
            if not self.line.strip() or self.line.strip() == "|":
                return preview_emit(
                    render_table(self._table_lines, self.width, self.color, light=self.light),
                    suppress_bullet=True,
                )
            if is_table_body_row(self.line):
                return preview_emit(
                    render_table(self._table_lines + [self.line], self.width, self.color, light=self.light),
                    suppress_bullet=True,
                )
            out = preview_emit(
                render_table(self._table_lines, self.width, self.color, light=self.light),
                suppress_bullet=True,
            )
            list_indents.clear()
            quote_indents.clear()
            out.extend(preview_non_table(self.line))
            return out

        if len(self._table_lines) == 1:
            header_cells, _ = split_table_cells(self._table_lines[0])
            if self.line.strip() and parse_table_alignments(self.line, len(header_cells)) is not None:
                return preview_emit(
                    render_table(
                        [self._table_lines[0], self.line], self.width, self.color, light=self.light,
                    ),
                    suppress_bullet=True,
                )
            out = preview_non_table(self._table_lines[0])
            if self.line.strip():
                out.extend(preview_non_table(self.line))
            return out

        return preview_non_table(self.line)

    def finish(self) -> list[str]:
        rows: list[str] = []
        if self._pending_escape:
            *complete, self.line = (self.line + sanitize_text(self._pending_escape)).split("\n")
            self._pending_escape = ""
            for line in complete:
                if self.markdown:
                    rows.extend(self._commit_markdown_line(line))
                else:
                    rows.extend(self._rows_plain(wrap(line, self.width)[self.committed :]))
                    self.committed = 0
        if self.markdown:
            if self.line:
                rows.extend(self._commit_markdown_line(self.line))
            rows.extend(self._flush_table())
        else:
            rows.extend(self._rows_plain(wrap(self.line, self.width)[self.committed :]))
        self.line = ""
        self.committed = 0
        self.blank_rows = 0
        self.fence = None
        self._list_indents.clear()
        self._quote_list_indents.clear()
        self._table_lines.clear()
        return rows


def format_tokens(count: int) -> str:
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)


def usage_cell(usage: dict[str, int], width: int, color: bool = True) -> list[str]:
    label = " · ".join(
        f"{label} {format_tokens(usage[key])}" for key, label in TOKEN_USAGE_FIELDS if key in usage
    )
    return ["  " + sgr(row, DIM, color) for row in wrap(label, width - 2)]
