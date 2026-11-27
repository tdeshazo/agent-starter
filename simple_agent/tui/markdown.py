"""Parse and format streamed Markdown blocks, lists, inline spans, and tables."""
import re

from prompt_toolkit.utils import get_cwidth

BOLD = "1"
DIM = "2"
ITALIC = "3"
UNDERLINE = "4"
STRIKE = "9"
BOLD_ITALIC = "1;3"
CYAN = "36"

BULLETS = ("•", "◦", "▪")

WORD = re.compile(r"([^\S\n]*)(\S+)")
ATOM_RE = re.compile(
    r"\\([\\*_`~[\]()#|+\-!])"
    r"|(?<!`)(`+)(?!`)(.+?)(?<!`)\2(?!`)"
    r"|(\ue000|\ue001)"
)
PLACEHOLDER_RE = re.compile(r"\ue000(\d+)\ue001")
SPAN_RE = re.compile(
    r"\[([^\[\]]+)\]\(([^()\s]*(?:\([^()\s]*\)[^()\s]*)*)\)"
    r"|\*\*\*(?![*\s])(.+?)(?<![*\s/])\*\*\*(?!\*)"
    r"|(?<!\w)___(?![_\s])(.+?)(?<![_\s])___(?!\w)"
    r"|\*\*(?=\S)(.+?)(?<![\s/])\*\*(?!\*)"
    r"|(?<!\w)__(?![_\s])(.+?)(?<![_\s])__(?!\w)"
    r"|(?<![*\w])\*(?![*\s])(.+?)(?<![*\s/])\*(?![*\w])"
    r"|(?<!\w)_(?![_\s])(.+?)(?<![_\s])_(?!\w)"
    r"|~~(?![~\s])(.+?)(?<![~\s])~~"
)

QUOTE_PREFIX = re.compile(r"^(\s{0,3})(?:>\s?)+")
THEMATIC_BREAK = re.compile(r"^\s{0,3}(?:(?:-\s*){3,}|(?:\*\s*){3,}|(?:_\s*){3,})$")
ATX_HEADING = re.compile(r"^(\s{0,3})(#{1,6})\s+(.*?)(?:\s+#+\s*)?$")
UNORDERED_ITEM = re.compile(r"^(\s*)([-*+•◦▪])(\s+)(.*)$")
ORDERED_ITEM = re.compile(r"^(\s*)(\d{1,9}[.)])(\s+)(.*)$")
TASK_ITEM = re.compile(r"^\[([ xX])\](\s+)(.*)$")
CELL_BULLET = re.compile(r"^([-*+•◦▪])\s+(.*)$")
TABLE_DELIM_CELL = re.compile(r"^:?-{1,}:?$")
TABLE_DELIM_CHARS = frozenset(" \t|:-")
BR_TAG = re.compile(r"<br\s*/?>", re.IGNORECASE)


def sgr(text: str, codes: str, color: bool = True) -> str:
    """Wrap text in an ANSI style when color is enabled."""
    if color and codes and text:
        return f"\x1b[{codes}m{text}\x1b[0m"
    return text


def combine_sgr(base: str, extra: str) -> str:
    """Combine two semicolon-delimited SGR code strings without duplicates."""
    if not base:
        return extra
    if not extra:
        return base
    parts = base.split(";")
    for code in extra.split(";"):
        if code and code not in parts:
            parts.append(code)
    return ";".join(parts)


def split_width(text: str, width: int) -> tuple[str, str]:
    """Split text after the longest prefix that fits in width columns."""
    used = 0
    for index, char in enumerate(text):
        used += get_cwidth(char)
        if used > width:
            return text[: max(index, 1)], text[max(index, 1) :]
    return text, ""


def wrap_ranges(plain: str, width: int) -> list[tuple[int, int]]:
    """Return contiguous slice ranges word-wrapping ``plain`` to ``width`` columns."""
    width = max(width, 1)
    ranges: list[tuple[int, int]] = []
    row_start = 0
    row_end = 0
    has_row = False
    for match in WORD.finditer(plain):
        space_start, _ = match.span(1)
        word_start, word_end = match.span(2)
        if has_row:
            cand_start, cand_end = row_start, word_end
        elif ranges:
            cand_start, cand_end = word_start, word_end
        else:
            cand_start, cand_end = space_start, word_end
        if get_cwidth(plain[cand_start:cand_end]) <= width:
            row_start, row_end = cand_start, cand_end
            has_row = True
            continue
        if has_row:
            ranges.append((row_start, row_end))
        cur = word_start
        while get_cwidth(plain[cur:word_end]) > width:
            head, _ = split_width(plain[cur:word_end], width)
            ranges.append((cur, cur + len(head)))
            cur += len(head)
        row_start, row_end = cur, word_end
        has_row = True
    if has_row or not ranges:
        ranges.append((row_start, row_end))
    return ranges


def fence_transition(
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


def _coalesce_spans(spans: list[tuple[str, str]]) -> list[tuple[str, str]]:
    merged: list[tuple[str, str]] = []
    for text, style in spans:
        if not text:
            continue
        if merged and merged[-1][1] == style:
            merged[-1] = (merged[-1][0] + text, style)
        else:
            merged.append((text, style))
    return merged


def _expand_atoms(
    chunk: str, style: str, atoms: list[tuple[str, str]]
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    pos = 0
    for match in PLACEHOLDER_RE.finditer(chunk):
        if match.start() > pos:
            out.append((chunk[pos : match.start()], style))
        atom_text, atom_style = atoms[int(match.group(1))]
        out.append((atom_text, combine_sgr(style, atom_style)))
        pos = match.end()
    if pos < len(chunk):
        out.append((chunk[pos:], style))
    return out


def _expand_atoms_plain(chunk: str, atoms: list[tuple[str, str]]) -> str:
    return PLACEHOLDER_RE.sub(lambda m: atoms[int(m.group(1))][0], chunk)


def parse_inline(text: str, base_style: str = "") -> list[tuple[str, str]]:
    """Parse inline Markdown spans into ``(plain_text, sgr_style)`` segments."""
    if not text:
        return []
    atoms: list[tuple[str, str]] = []

    def replace_atom(match: re.Match[str]) -> str:
        idx = len(atoms)
        if match.group(1) is not None:
            atoms.append((match.group(1), ""))
        elif match.group(2) is not None:
            inner = match.group(3)
            if len(inner) >= 2 and inner[0] == " " and inner[-1] == " " and inner.strip(" "):
                inner = inner[1:-1]
            atoms.append((inner, CYAN))
        else:
            atoms.append((match.group(4), ""))
        return f"\ue000{idx}\ue001"

    masked = ATOM_RE.sub(replace_atom, text)

    def parse_masked(segment: str, style: str) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        pos = 0
        for match in SPAN_RE.finditer(segment):
            if match.start() > pos:
                out.extend(_expand_atoms(segment[pos : match.start()], style, atoms))
            if match.group(1) is not None:
                label_spans = parse_masked(match.group(1), combine_sgr(style, UNDERLINE))
                out.extend(label_spans)
                url_plain = _expand_atoms_plain(match.group(2), atoms)
                label_plain = "".join(part for part, _ in label_spans)
                if url_plain and url_plain != label_plain and url_plain != f"mailto:{label_plain}":
                    out.append((f" ({url_plain})", combine_sgr(style, DIM)))
            elif (inner := match.group(3) or match.group(4)) is not None:
                out.extend(parse_masked(inner, combine_sgr(style, BOLD_ITALIC)))
            elif (inner := match.group(5) or match.group(6)) is not None:
                out.extend(parse_masked(inner, combine_sgr(style, BOLD)))
            elif (inner := match.group(7) or match.group(8)) is not None:
                out.extend(parse_masked(inner, combine_sgr(style, ITALIC)))
            elif (inner := match.group(9)) is not None:
                out.extend(parse_masked(inner, combine_sgr(style, STRIKE)))
            pos = match.end()
        if pos < len(segment):
            out.extend(_expand_atoms(segment[pos:], style, atoms))
        return out

    return _coalesce_spans(parse_masked(masked, base_style))


def spans_width(spans: list[tuple[str, str]]) -> int:
    """Return total display column width of parsed inline spans."""
    return sum(get_cwidth(part) for part, _ in spans)


def wrap_spans(
    spans: list[tuple[str, str]], width: int, color: bool = True
) -> list[tuple[str, int]]:
    """Word-wrap styled spans, returning ``(ansi_row, display_width)`` pairs."""
    plain = "".join(part for part, _ in spans)
    if not plain:
        return [("", 0)]
    out: list[tuple[str, int]] = []
    for start, end in wrap_ranges(plain, width):
        pieces: list[tuple[str, str]] = []
        offset = 0
        for part, style in spans:
            next_offset = offset + len(part)
            if next_offset > start and offset < end:
                sub = part[max(start - offset, 0) : min(end - offset, len(part))]
                if sub:
                    if pieces and pieces[-1][1] == style:
                        pieces[-1] = (pieces[-1][0] + sub, style)
                    else:
                        pieces.append((sub, style))
            offset = next_offset
            if offset >= end:
                break
        vis_width = sum(get_cwidth(sub) for sub, _ in pieces)
        rendered = "".join(sgr(sub, style, color) for sub, style in pieces)
        out.append((rendered, vis_width))
    return out


def _push_list_level(
    list_stack: list[tuple[int, int]],
    raw_indent: int,
    marker_width: int,
    width: int,
    *,
    allow_align_pad: bool = False,
) -> tuple[int, int, int]:
    """Update ``list_stack`` and return ``(level, display_indent, hang_width)``."""
    if not list_stack:
        if raw_indent == 0:
            display_indent = 0
        elif allow_align_pad and raw_indent == 1:
            display_indent = 1
        else:
            list_stack.append((0, 2))
            display_indent = 2
    else:
        while list_stack and list_stack[-1][0] > raw_indent:
            list_stack.pop()
        if list_stack and list_stack[-1][0] == raw_indent:
            list_stack.pop()
        display_indent = list_stack[-1][1] if list_stack else 0

    max_indent = max(width - marker_width - 4, 0)
    display_indent = min(display_indent, max_indent)
    level = len(list_stack)
    hang_width = display_indent + marker_width
    list_stack.append((raw_indent, hang_width))
    return level, display_indent, hang_width


def render_markdown_line(
    line: str,
    width: int,
    list_stack: list[tuple[int, int]],
    quote_list_stack: list[tuple[int, int]],
    color: bool = True,
) -> tuple[list[str], bool]:
    """Render a single non-fence, non-table Markdown line.

    Returns ``(rows, suppress_cell_bullet)``.
    """
    expanded = line.expandtabs(4)
    if not expanded.strip():
        quote_list_stack.clear()
        return [], False

    if quote_match := QUOTE_PREFIX.match(expanded):
        list_stack.clear()
        depth = quote_match.group(0).count(">")
        eff_depth = min(depth, max((width - 2) // 2, 1)) if width >= 4 else 0
        bar = sgr("│ ", DIM, color) * eff_depth
        inner = expanded[quote_match.end() :]
        if not inner.strip():
            quote_list_stack.clear()
            return [sgr(("│ " * eff_depth).rstrip(), DIM, color)], False
        inner_width = max(width - 2 * eff_depth, 1)
        inner_rows, _ = render_markdown_line(inner, inner_width, quote_list_stack, [], color)
        return [bar + row for row in inner_rows], False

    quote_list_stack.clear()

    if THEMATIC_BREAK.match(expanded):
        list_stack.clear()
        return [sgr("─" * max(width, 1), DIM, color)], False

    if heading_match := ATX_HEADING.match(expanded):
        list_stack.clear()
        spans = parse_inline(heading_match.group(3), base_style=BOLD)
        if not spans:
            return [], False
        return [styled for styled, _ in wrap_spans(spans, width, color)], False

    if unordered_match := UNORDERED_ITEM.match(expanded):
        raw_indent = len(unordered_match.group(1))
        body = unordered_match.group(4)
        task_match = TASK_ITEM.match(body)
        level, display_indent, hang_width = _push_list_level(
            list_stack, raw_indent, 2, width
        )
        if task_match:
            checked = task_match.group(1) in {"x", "X"}
            marker = (sgr("☑", BOLD, color) if checked else sgr("☐", DIM, color)) + " "
            body = task_match.group(3)
        else:
            marker = BULLETS[level % len(BULLETS)] + " "
        first_prefix = " " * display_indent + marker
        rest_prefix = " " * hang_width
        if not body.strip():
            return [first_prefix.rstrip()], True
        spans = parse_inline(body)
        wrapped = wrap_spans(spans, max(width - hang_width, 1), color)
        rows = [
            (first_prefix if idx == 0 else rest_prefix) + styled
            for idx, (styled, _) in enumerate(wrapped)
        ]
        return rows, True

    if ordered_match := ORDERED_ITEM.match(expanded):
        raw_indent = len(ordered_match.group(1))
        marker_plain = ordered_match.group(2) + " "
        body = ordered_match.group(4)
        _, display_indent, hang_width = _push_list_level(
            list_stack, raw_indent, len(marker_plain), width, allow_align_pad=True
        )
        if task_match := TASK_ITEM.match(body):
            checked = task_match.group(1) in {"x", "X"}
            checkbox = (sgr("☑", BOLD, color) if checked else sgr("☐", DIM, color)) + " "
            body = task_match.group(3)
        else:
            checkbox = ""
        first_prefix = " " * display_indent + marker_plain + checkbox
        extra = 2 if checkbox else 0
        eff_hang = hang_width + extra
        rest_prefix = " " * eff_hang
        if not body.strip():
            return [first_prefix.rstrip()], True
        spans = parse_inline(body)
        wrapped = wrap_spans(spans, max(width - eff_hang, 1), color)
        rows = [
            (first_prefix if idx == 0 else rest_prefix) + styled
            for idx, (styled, _) in enumerate(wrapped)
        ]
        return rows, True

    raw_indent = len(expanded) - len(expanded.lstrip(" "))
    if list_stack and raw_indent >= 2:
        while len(list_stack) > 1 and raw_indent <= list_stack[-1][0]:
            list_stack.pop()
        hang_width = min(list_stack[-1][1], max(width - 4, 0))
        prefix = " " * hang_width
        spans = parse_inline(expanded.lstrip(" "))
        wrapped = wrap_spans(spans, max(width - hang_width, 1), color)
        return [prefix + styled for styled, _ in wrapped], True

    list_stack.clear()
    spans = parse_inline(expanded)
    return [styled for styled, _ in wrap_spans(spans, width, color)], False


def _find_closing_backticks(text: str, start: int, count: int) -> int:
    """Find the end index of a matching backtick run of exact length ``count``."""
    pos = start
    target = "`" * count
    while True:
        idx = text.find(target, pos)
        if idx == -1:
            return -1
        before_ok = idx == 0 or text[idx - 1] != "`"
        after_end = idx + count
        after_ok = after_end == len(text) or text[after_end] != "`"
        if before_ok and after_ok:
            return after_end
        pos = idx + 1


def split_table_cells(line: str) -> tuple[list[str], bool]:
    """Split a GFM pipe-table row on unescaped, non-code-span ``|`` characters."""
    stripped = line.strip()
    if "|" not in stripped:
        return [], False
    cells: list[str] = []
    buf: list[str] = []
    has_pipe = False
    started_with_pipe = False
    ended_with_pipe = False
    idx = 0
    length = len(stripped)
    while idx < length:
        char = stripped[idx]
        if char == "\\":
            ended_with_pipe = False
            if idx + 1 < length:
                buf.append(stripped[idx : idx + 2])
                idx += 2
                continue
            buf.append(char)
            idx += 1
            continue
        if char == "`":
            ended_with_pipe = False
            run_end = idx
            while run_end < length and stripped[run_end] == "`":
                run_end += 1
            close_end = _find_closing_backticks(stripped, run_end, run_end - idx)
            if close_end != -1:
                buf.append(stripped[idx:close_end].replace(r"\|", "|"))
                idx = close_end
                continue
            buf.append(stripped[idx:run_end])
            idx = run_end
            continue
        if char == "|":
            if idx == 0:
                started_with_pipe = True
            has_pipe = True
            ended_with_pipe = True
            cells.append("".join(buf))
            buf = []
            idx += 1
            continue
        if not char.isspace():
            ended_with_pipe = False
        buf.append(char)
        idx += 1
    cells.append("".join(buf))
    if not has_pipe:
        return [], False
    if started_with_pipe:
        cells = cells[1:]
    if ended_with_pipe and cells:
        cells = cells[:-1]
    return [cell.strip() for cell in cells], True


def can_be_table_delimiter_prefix(line: str) -> bool:
    """Check whether a partial streamed line can still become a table delimiter row."""
    return all(char in TABLE_DELIM_CHARS for char in line)


def parse_table_alignments(line: str, expected_cols: int) -> list[str] | None:
    """Parse column alignments from a GFM table delimiter row, or return ``None``."""
    cells, has_pipe = split_table_cells(line)
    if not has_pipe or not cells or len(cells) != expected_cols:
        return None
    if not line.lstrip().startswith("|") and len(cells) < 2:
        return None
    alignments: list[str] = []
    for cell in cells:
        if not TABLE_DELIM_CELL.match(cell):
            return None
        if cell.startswith(":") and cell.endswith(":"):
            alignments.append("center")
        elif cell.endswith(":"):
            alignments.append("right")
        else:
            alignments.append("left")
    return alignments


def is_table_header_candidate(line: str) -> bool:
    """Check whether ``line`` can be the header row of a GFM pipe table."""
    if not line.strip() or fence_transition(line, None)[0]:
        return False
    expanded = line.expandtabs(4)
    if (
        QUOTE_PREFIX.match(expanded)
        or THEMATIC_BREAK.match(expanded)
        or ATX_HEADING.match(expanded)
        or UNORDERED_ITEM.match(expanded)
        or ORDERED_ITEM.match(expanded)
    ):
        return False
    cells, has_pipe = split_table_cells(line)
    if not has_pipe or not cells:
        return False
    if not line.lstrip().startswith("|") and len(cells) < 2:
        return False
    return parse_table_alignments(line, len(cells)) is None


def is_table_body_row(line: str) -> bool:
    """Check whether ``line`` continues an active GFM pipe table."""
    if not line.strip() or fence_transition(line, None)[0]:
        return False
    expanded = line.expandtabs(4)
    if (
        QUOTE_PREFIX.match(expanded)
        or THEMATIC_BREAK.match(expanded)
        or ATX_HEADING.match(expanded)
    ):
        return False
    if not line.lstrip().startswith("|") and (
        UNORDERED_ITEM.match(expanded) or ORDERED_ITEM.match(expanded)
    ):
        return False
    cells, has_pipe = split_table_cells(line)
    return has_pipe and bool(cells)


def _split_cell_lines(raw_cell: str) -> list[str]:
    """Split a table cell on ``<br>`` tags outside inline backtick spans."""
    if "<" not in raw_cell:
        return [raw_cell]
    parts: list[str] = []
    buf: list[str] = []
    idx = 0
    length = len(raw_cell)
    while idx < length:
        if raw_cell[idx] == "`":
            run_end = idx
            while run_end < length and raw_cell[run_end] == "`":
                run_end += 1
            close_end = _find_closing_backticks(raw_cell, run_end, run_end - idx)
            if close_end != -1:
                buf.append(raw_cell[idx:close_end])
                idx = close_end
                continue
            buf.append(raw_cell[idx:run_end])
            idx = run_end
            continue
        if raw_cell[idx] == "<" and (br_match := BR_TAG.match(raw_cell, idx)):
            parts.append("".join(buf).strip())
            buf = []
            idx = br_match.end()
            continue
        buf.append(raw_cell[idx])
        idx += 1
    parts.append("".join(buf).strip())
    return parts


def _parse_cell_sublines(
    raw_cell: str, base_style: str, color: bool
) -> list[tuple[str, int, list[tuple[str, str]]]]:
    """Parse cell lines into ``(styled_prefix, prefix_width, spans)`` tuples."""
    parsed: list[tuple[str, int, list[tuple[str, str]]]] = []
    for sub in _split_cell_lines(raw_cell.expandtabs(4)):
        if bullet_match := CELL_BULLET.match(sub):
            body = bullet_match.group(2)
            if task_match := TASK_ITEM.match(body):
                checked = task_match.group(1) in {"x", "X"}
                mark_style = combine_sgr(base_style, BOLD if checked else DIM)
                prefix = sgr("☑" if checked else "☐", mark_style, color) + " "
                parsed.append((prefix, 2, parse_inline(task_match.group(3), base_style=base_style)))
                continue
            prefix = sgr("• ", base_style, color)
            parsed.append((prefix, 2, parse_inline(body, base_style=base_style)))
        elif task_match := TASK_ITEM.match(sub):
            checked = task_match.group(1) in {"x", "X"}
            mark_style = combine_sgr(base_style, BOLD if checked else DIM)
            prefix = sgr("☑" if checked else "☐", mark_style, color) + " "
            parsed.append((prefix, 2, parse_inline(task_match.group(3), base_style=base_style)))
        else:
            parsed.append(("", 0, parse_inline(sub, base_style=base_style)))
    return parsed or [("", 0, [])]


def _longest_word_width(
    sublines: list[tuple[str, int, list[tuple[str, str]]]]
) -> int:
    best = 0
    for _, pfx_w, spans in sublines:
        plain = "".join(part for part, _ in spans)
        first = True
        for match in WORD.finditer(plain):
            word_w = get_cwidth(match.group(2)) + (pfx_w if first else 0)
            best = max(best, word_w)
            first = False
    return best


def _allocate_column_widths(
    natural: list[int], min_words: list[int], budget: int
) -> list[int]:
    if sum(natural) <= budget:
        return natural.copy()
    floors = [min(nat, max(mw, 3)) for nat, mw in zip(natural, min_words, strict=True)]
    total_floor = sum(floors)
    while total_floor > budget:
        widest_idx = max(range(len(floors)), key=floors.__getitem__)
        if floors[widest_idx] <= 1:
            break
        floors[widest_idx] -= 1
        total_floor -= 1

    remaining = max(budget - total_floor, 0)
    needs = [max(nat - flr, 0) for nat, flr in zip(natural, floors, strict=True)]
    total_need = sum(needs)
    if total_need == 0 or remaining == 0:
        return floors

    widths = [
        flr + (remaining * need) // total_need
        for flr, need in zip(floors, needs, strict=True)
    ]
    leftover = budget - sum(widths)
    if leftover > 0:
        order = sorted(
            range(len(needs)),
            key=lambda idx: ((remaining * needs[idx]) % total_need, needs[idx]),
            reverse=True,
        )
        for idx in order:
            if leftover == 0:
                break
            if widths[idx] < natural[idx]:
                widths[idx] += 1
                leftover -= 1
    return widths


def _align_cell(styled: str, vis_width: int, col_width: int, alignment: str) -> str:
    pad = max(col_width - vis_width, 0)
    if alignment == "right":
        return " " * pad + styled
    if alignment == "center":
        left = pad // 2
        return " " * left + styled + " " * (pad - left)
    return styled + " " * pad


def render_table(table_lines: list[str], width: int, color: bool = True) -> list[str]:
    """Render a GFM pipe table with rounded borders, alignment, and cell wrapping."""
    if len(table_lines) < 2:
        return []
    header_raw, _ = split_table_cells(table_lines[0])
    if not header_raw:
        return []
    col_count = len(header_raw)
    alignments = parse_table_alignments(table_lines[1], col_count) or ["left"] * col_count
    body_raw_rows: list[list[str]] = []
    for raw_line in table_lines[2:]:
        cells, has_pipe = split_table_cells(raw_line)
        if not has_pipe:
            continue
        if len(cells) < col_count:
            cells = cells + [""] * (col_count - len(cells))
        elif len(cells) > col_count:
            cells = cells[:col_count]
        body_raw_rows.append(cells)

    header_cells = [_parse_cell_sublines(cell, BOLD, color) for cell in header_raw]
    body_cells = [
        [_parse_cell_sublines(cell, "", color) for cell in row]
        for row in body_raw_rows
    ]

    # Stacked fallback when the terminal is too narrow for even compact columns.
    if width < 4 * col_count + 1:
        stacked: list[str] = []
        rows_to_stack = body_raw_rows or [header_raw]
        for row_idx, row in enumerate(rows_to_stack):
            if row_idx > 0:
                stacked.append(sgr("─" * max(width, 1), DIM, color))
            for col_idx, value in enumerate(row):
                label = header_raw[col_idx]
                entry = f"**{label}**: {value}" if body_raw_rows and label else (value or label)
                if entry:
                    spans = parse_inline(entry)
                    stacked.extend(styled for styled, _ in wrap_spans(spans, width, color))
        return stacked

    cell_pad = 1 if width >= 6 * col_count + 1 else 0
    overhead = (1 + 2 * cell_pad) * col_count + 1
    budget = max(width - overhead, col_count)

    natural: list[int] = []
    min_words: list[int] = []
    for col_idx in range(col_count):
        col_sublines = list(header_cells[col_idx])
        for row in body_cells:
            col_sublines.extend(row[col_idx])
        nat = max((pfx_w + spans_width(spans) for _, pfx_w, spans in col_sublines), default=1)
        natural.append(max(nat, 1))
        hdr_word = _longest_word_width(header_cells[col_idx])
        body_word = _longest_word_width(
            [sub for row in body_cells for sub in row[col_idx]]
        )
        min_words.append(min(max(nat, 1), max(min(hdr_word, 20), min(body_word, 16), 3)))

    col_widths = _allocate_column_widths(natural, min_words, budget)

    def border(text: str) -> str:
        return sgr(text, DIM, color)

    def rule(left: str, mid: str, right: str) -> str:
        segments = ["─" * (col_w + 2 * cell_pad) for col_w in col_widths]
        return border(left + mid.join(segments) + right)

    pad_str = " " * cell_pad
    sep = border("│")

    def format_row(
        row_cells: list[list[tuple[str, int, list[tuple[str, str]]]]]
    ) -> list[str]:
        wrapped_cols: list[list[tuple[str, int]]] = []
        for col_idx, sublines in enumerate(row_cells):
            col_w = col_widths[col_idx]
            col_wrapped: list[tuple[str, int]] = []
            for pfx, pfx_w, spans in sublines:
                if pfx_w and col_w >= pfx_w + 3:
                    hang = " " * pfx_w
                    sub_wrapped = wrap_spans(spans, col_w - pfx_w, color)
                    for idx, (styled, vis_w) in enumerate(sub_wrapped):
                        lead = pfx if idx == 0 else hang
                        if not styled and idx == 0:
                            col_wrapped.append((pfx.rstrip(), max(pfx_w - 1, 0)))
                        else:
                            col_wrapped.append((lead + styled, pfx_w + vis_w))
                else:
                    col_wrapped.extend(wrap_spans(spans, col_w, color))
            wrapped_cols.append(col_wrapped or [("", 0)])
        height = max(len(col) for col in wrapped_cols)
        rendered_lines: list[str] = []
        for line_idx in range(height):
            parts: list[str] = []
            for col_idx, col_wrapped in enumerate(wrapped_cols):
                styled, vis_w = (
                    col_wrapped[line_idx] if line_idx < len(col_wrapped) else ("", 0)
                )
                aligned = _align_cell(styled, vis_w, col_widths[col_idx], alignments[col_idx])
                parts.append(pad_str + aligned + pad_str)
            rendered_lines.append(sep + sep.join(parts) + sep)
        return rendered_lines

    out = [rule("╭", "┬", "╮")]
    out.extend(format_row(header_cells))
    if body_cells:
        out.append(rule("├", "┼", "┤"))
        for row in body_cells:
            out.extend(format_row(row))
    out.append(rule("╰", "┴", "╯"))
    return out
