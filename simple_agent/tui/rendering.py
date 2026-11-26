"""Render terminal headers, transcript cells, and streamed text."""
import json
import re
import unicodedata

from prompt_toolkit.utils import get_cwidth

from ..settings import DEFAULT_AGENT_NAME
from .pets import DEFAULT_PET, PET_GAP, pet_rows, pet_width


TOOL_RESULT_LINES = 3
MAX_ESCAPE_BUFFER = 256

BOLD = "1"
DIM = "2"
ITALIC_DIM = "2;3"
CYAN = "36"
BOLD_CYAN = "1;36"
RED = "31"

WORD = re.compile(r"([^\S\n]*)(\S+)")
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
TOKEN_USAGE_FIELDS = (
    ("inputTokens", "in"),
    ("cacheReadInputTokens", "cached"),
    ("outputTokens", "out"),
)


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


def sgr(text: str, codes: str, color: bool = True) -> str:
    """Wrap text in an ANSI style when color is enabled."""
    if color and codes and text:
        return f"\x1b[{codes}m{text}\x1b[0m"
    return text


def _split_width(text: str, width: int) -> tuple[str, str]:
    """Split text after the longest prefix that fits in width columns."""
    used = 0
    for index, char in enumerate(text):
        used += get_cwidth(char)
        if used > width:
            return text[: max(index, 1)], text[max(index, 1) :]
    return text, ""


def wrap(text: str, width: int) -> list[str]:
    """Word-wrap one logical line by display width.

    Leading indentation is kept, words longer than a row start a new row and are
    broken there. Rows other than the last never change when text is appended,
    which lets streamed rows be committed to the transcript as soon as they fill.
    """
    width = max(width, 1)
    rows: list[str] = []
    row = ""
    for match in WORD.finditer(text.expandtabs(4)):
        space, word = match.groups()
        if row:
            candidate = row + space + word
        elif rows:
            candidate = word
        else:
            candidate = space + word
        if get_cwidth(candidate) <= width:
            row = candidate
            continue
        if row:
            rows.append(row)
        while get_cwidth(word) > width:
            head, word = _split_width(word, width)
            rows.append(head)
        row = word
    if row or not rows:
        rows.append(row)
    return rows


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


def user_cell(text: str, width: int, color: bool = True) -> list[str]:
    clean = sanitize_text(text)
    rows = [row for line in clean.strip("\n").split("\n") for row in wrap(line, width - 2)]
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


def tool_result_rows(result: dict, width: int, color: bool = True) -> list[str]:
    parts = []
    for block in result.get("content", []):
        if "text" in block:
            parts.append(sanitize_text(str(block["text"])))
        elif "json" in block:
            parts.append(sanitize_text(json.dumps(block["json"], ensure_ascii=False)))
        else:
            kind = sanitize_text(str(next(iter(block), "content")), multiline=False)
            parts.append(f"[{kind}]")
    lines = [line for line in "\n".join(parts).splitlines() if line.strip()] or ["(no output)"]
    shown = lines[:TOOL_RESULT_LINES]
    hidden = len(lines) - len(shown)
    if hidden:
        shown.append(f"… +{hidden} lines")
    style = RED if result.get("status") == "error" else DIM
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


INLINE = re.compile(r"(\*\*|`)")
HEADING = re.compile(r"^(\s*)#{1,6} ")


def render_inline(row: str, state: tuple[bool, bool], color: bool = True) -> tuple[str, tuple[bool, bool]]:
    """Style **bold** and `code` spans, carrying open spans across rows."""
    bold, code = state
    out = []
    for part in INLINE.split(row):
        if part == "`":
            code = not code
        elif part == "**" and not code:
            bold = not bold
        else:
            out.append(sgr(part, CYAN if code else (BOLD if bold else ""), color))
    return "".join(out), (bold, code)


def _fence_transition(
    line: str, active: tuple[str, int] | None
) -> tuple[bool, tuple[str, int] | None]:
    """Check whether ``line`` opens or closes a CommonMark code fence."""
    stripped = line.lstrip()
    if active is None:
        if stripped.startswith("```"):
            count = len(stripped) - len(stripped.lstrip("`"))
            if "`" not in stripped[count:]:
                return True, ("`", count)
        elif stripped.startswith("~~~"):
            count = len(stripped) - len(stripped.lstrip("~"))
            return True, ("~", count)
        return False, None
    char, min_len = active
    if stripped.startswith(char * min_len):
        count = len(stripped) - len(stripped.lstrip(char))
        if not stripped[count:].strip():
            return True, None
    return False, active


class StreamCell:
    """Wrap streamed text, committing rows once later text cannot change them."""

    def __init__(self, width: int, bullet: str, style: str = "", color: bool = True, markdown: bool = False):
        self.width = max(width - 2, 1)
        self.bullet = bullet
        self.style = style
        self.color = color
        self.markdown = markdown
        self.line = ""
        self.committed = 0
        self.started = False
        self.blank_rows = 0
        self.fence: tuple[str, int] | None = None
        self.inline = (False, False)
        self._pending_escape = ""

    @property
    def in_fence(self) -> bool:
        return self.fence is not None

    def _style(self, line: str, row: str, commit: bool) -> str:
        if not self.markdown:
            return sgr(row, self.style, self.color)
        is_fence, _ = _fence_transition(line, self.fence)
        if is_fence:
            return sgr(row, DIM, self.color)
        if self.fence is not None:
            return row
        stripped = line.lstrip()
        if HEADING.match(stripped):
            return sgr(INLINE.sub("", HEADING.sub(r"\1", row)), BOLD, self.color)
        text, state = render_inline(row, self.inline, self.color)
        if commit:
            self.inline = state
        return text

    def _prefix(self) -> str:
        return "  " if self.started else self.bullet + " "

    def _rows(self, line: str, rows: list[str]) -> list[str]:
        out = []
        for row in rows:
            if not row.strip():
                if self.started:
                    self.blank_rows += 1
                continue
            out.extend([""] * self.blank_rows)
            self.blank_rows = 0
            out.append(self._prefix() + self._style(line, row, commit=True))
            self.started = True
        return out

    def _end_line(self, line: str) -> None:
        if self.markdown:
            _, self.fence = _fence_transition(line, self.fence)
        self.inline = (False, False)

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
        rows = []
        for line in complete:
            rows.extend(self._rows(line, wrap(line, self.width)[self.committed :]))
            self.committed = 0
            self._end_line(line)
        current = wrap(self.line, self.width)
        rows.extend(self._rows(self.line, current[self.committed : len(current) - 1]))
        self.committed = max(self.committed, len(current) - 1)
        return rows

    def tail(self) -> list[str]:
        """Return the row still being written, as it would appear if committed."""
        row = wrap(self.line, self.width)[-1]
        if not row.strip():
            return []
        blanks = [""] * self.blank_rows if self.started else []
        return blanks + [self._prefix() + self._style(self.line, row, commit=False)]

    def finish(self) -> list[str]:
        rows = []
        if self._pending_escape:
            *complete, self.line = (self.line + sanitize_text(self._pending_escape)).split("\n")
            self._pending_escape = ""
            for line in complete:
                rows.extend(self._rows(line, wrap(line, self.width)[self.committed :]))
                self.committed = 0
                self._end_line(line)
        rows.extend(self._rows(self.line, wrap(self.line, self.width)[self.committed :]))
        self.line = ""
        self.committed = 0
        self.blank_rows = 0
        self.fence = None
        self.inline = (False, False)
        return rows


def format_tokens(count: int) -> str:
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)


def usage_cell(usage: dict[str, int], width: int, color: bool = True) -> list[str]:
    label = " · ".join(f"{label} {format_tokens(usage[key])}" for key, label in TOKEN_USAGE_FIELDS if key in usage)
    return ["  " + sgr(row, DIM, color) for row in wrap(label, width - 2)]
