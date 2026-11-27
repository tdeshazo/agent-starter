"""Render and select transcript text without taking focus from the composer."""
import time
import unicodedata
from bisect import bisect_right
from collections.abc import Callable
from functools import cache

from prompt_toolkit.data_structures import Point
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import ANSI, fragment_list_to_text, to_formatted_text
from prompt_toolkit.layout.controls import UIContent, UIControl
from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType, MouseModifier


def _plain(row: str) -> str:
    return fragment_list_to_text(to_formatted_text(ANSI(row)))


def _word_bounds(line: str, column: int) -> tuple[int, int]:
    # prompt-toolkit's word regex splits combining accents from their letters.
    # Find boundaries without marks, then map back to the unchanged source text.
    starts = [index for index, char in enumerate(line) if not unicodedata.category(char).startswith("M")]
    if not starts:
        return 0, len(line)
    plain = "".join(line[index] for index in starts)
    cursor = max(0, bisect_right(starts, column) - 1)
    start, end = Document(plain, cursor).find_boundaries_of_current_word()
    boundaries = [*starts, len(line)]
    return boundaries[cursor + start], boundaries[cursor + end]


class TranscriptControl(UIControl):
    """Display live rows, freezing the painted text while it is selected.

    Window already translates mouse positions to logical rows and character
    offsets, including wide characters and lines wrapped by the terminal UI.
    Selection endpoints include the hit character: clicks past a row's end
    map to its last character, not an extra cursor cell.
    """

    def __init__(
        self,
        tail: Callable[[], list[str]],
        on_width_change: Callable[[int], None] | None = None,
        on_wheel: Callable[[int], None] | None = None,
        focusable: Callable[[], bool] | None = None,
        on_select: Callable[[], None] | None = None,
    ):
        self.rows: list[str] = []
        self.tail = tail
        self.on_width_change = on_width_change
        self.on_wheel = on_wheel
        self._focusable = focusable
        self._on_select = on_select
        self.first_line: int | None = None
        self._painted_rows: list[str] = []
        self._selection_rows: list[str] | None = None
        self._anchor = Point(0, 0)
        self._cursor = Point(0, 0)
        self._selected = False
        self._dragging = False
        self._last_click: tuple[float, Point] | None = None
        self._click_count = 0

    def is_focusable(self) -> bool:
        return self._focusable() if self._focusable is not None else False

    @property
    def has_selection(self) -> bool:
        return self._selected

    def clear_selection(self) -> None:
        self._selection_rows = None
        self._selected = self._dragging = False
        self._last_click = None
        self._click_count = 0

    def end_drag(self) -> None:
        """Handle a mouse release over another control without freezing a click."""
        self._dragging = False
        if not self.has_selection:
            self.clear_selection()

    def _bounds(self) -> tuple[Point, Point]:
        start, end = sorted((self._anchor, self._cursor), key=lambda point: (point.y, point.x))
        return start, Point(end.x + 1, end.y)

    def selected_text(self) -> str:
        """Return the selected visible text, without any ANSI styling."""
        if not self.has_selection or self._selection_rows is None:
            return ""
        start, end = self._bounds()
        lines = [_plain(row) for row in self._selection_rows[start.y : end.y + 1]]
        lines[-1] = lines[-1][:end.x]
        lines[0] = lines[0][start.x:]
        return "\n".join(lines)

    def _point(self, position: Point) -> Point:
        rows = self._selection_rows or self._painted_rows
        row = max(0, min(position.y, len(rows) - 1))
        column = max(0, min(position.x, max(len(_plain(rows[row])) - 1, 0)))
        return Point(column, row)

    def mouse_handler(self, mouse_event: MouseEvent):
        event_type = mouse_event.event_type
        if self.on_wheel is not None:
            if event_type == MouseEventType.SCROLL_UP:
                self.on_wheel(-1)
                return None
            if event_type == MouseEventType.SCROLL_DOWN:
                self.on_wheel(1)
                return None

        if event_type == MouseEventType.MOUSE_DOWN and mouse_event.button == MouseButton.LEFT:
            if not self._painted_rows:
                return NotImplemented
            if self._selection_rows is None:
                self._selection_rows = self._painted_rows
            point = self._point(mouse_event.position)
            extending = MouseModifier.SHIFT in mouse_event.modifiers and self.has_selection
            if not extending:
                self._anchor = point
            self._cursor = point
            self._selected = extending
            self._dragging = True
        elif event_type == MouseEventType.MOUSE_MOVE and self._dragging:
            if mouse_event.button not in {MouseButton.LEFT, MouseButton.UNKNOWN}:
                self._dragging = False
                if not self.has_selection:
                    self.clear_selection()
                return NotImplemented
            self._cursor = self._point(mouse_event.position)
            self._selected = self._cursor != self._anchor
        elif event_type == MouseEventType.MOUSE_UP and self._dragging:
            self._cursor = self._point(mouse_event.position)
            self._selected = self._selected or self._cursor != self._anchor
            self._dragging = False
            if not self._selected:
                now = time.monotonic()
                repeated = (
                    self._last_click is not None
                    and now - self._last_click[0] < 0.3
                    and self._last_click[1] == self._cursor
                )
                self._click_count = self._click_count % 3 + 1 if repeated else 1
                self._last_click = (now, self._cursor)
                line = _plain(self._selection_rows[self._cursor.y])
                if self._click_count == 2 and line:
                    start, end = _word_bounds(line, self._cursor.x)
                    self._anchor = Point(start, self._cursor.y)
                    self._cursor = Point(max(end - 1, start), self._cursor.y)
                    self._selected = True
                elif self._click_count == 3 and line:
                    self._anchor = Point(0, self._cursor.y)
                    self._cursor = Point(len(line) - 1, self._cursor.y)
                    self._selected = True
            else:
                self._last_click = None
                self._click_count = 0
            if not self._selected:
                self._selection_rows = None
        else:
            return NotImplemented

        if self._on_select is not None:
            self._on_select()
        return None

    def create_content(self, width: int, height: int | None) -> UIContent:
        if self.on_width_change is not None:
            self.on_width_change(width)
        rows = self._selection_rows
        if rows is None:
            # Copy references to immutable strings so a click always sees the
            # last paint, even if streamed rows were committed since rendering.
            rows = self.rows + self.tail()
        self._painted_rows = rows
        count = len(rows)
        if not count:
            return UIContent(line_count=1, show_cursor=False)
        bounds = self._bounds() if self.has_selection else None

        @cache
        def get_line(index: int):
            fragments = to_formatted_text(ANSI(rows[index]))
            # Empty rows need a mapped cell for mouse coordinates. This blank
            # is display-only; the copied row remains an empty string.
            if not fragment_list_to_text(fragments):
                fragments = [("", " ")]
            if bounds is None or not bounds[0].y <= index <= bounds[1].y:
                return fragments
            start, end = bounds
            left = start.x if index == start.y else 0
            right = end.x if index == end.y else len(fragment_list_to_text(fragments))
            selected = []
            offset = 0
            for style, text, *rest in fragments:
                if "[ZeroWidthEscape]" in style:
                    selected.append((style, text, *rest))
                    continue
                low = max(0, min(left - offset, len(text)))
                high = max(low, min(right - offset, len(text)))
                if low:
                    selected.append((style, text[:low], *rest))
                if high > low:
                    selected.append((style + " class:selected", text[low:high], *rest))
                if high < len(text):
                    selected.append((style, text[high:], *rest))
                offset += len(text)
            return selected

        if self.first_line is None:
            row = count - 1
            column = len(fragment_list_to_text(get_line(row)))
        else:
            row = min(self.first_line, count - 1)
            column = 0
        return UIContent(get_line, count, cursor_position=Point(column, row), show_cursor=False)
