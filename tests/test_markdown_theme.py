import unittest

from prompt_toolkit.formatted_text import ANSI, fragment_list_to_text, to_formatted_text
from prompt_toolkit.utils import get_cwidth

from simple_agent.tui.markdown import render_markdown_line, render_table
from simple_agent.tui.rendering import StreamCell


def plain(row: str) -> str:
    return fragment_list_to_text(to_formatted_text(ANSI(row)))


class MarkdownThemeTests(unittest.TestCase):
    def test_heading_levels_match_codex_palette_and_hierarchy(self):
        palettes = (
            (False, ("243;139;168", "250;179;135", "249;226;175")),
            (True, ("210;15;57", "188;74;8", "153;98;20")),
        )
        attributes = ("1;4", "1", "1;3", "3", "3", "3")
        for light, palette in palettes:
            for level, attrs in enumerate(attributes, start=1):
                with self.subTest(light=light, level=level):
                    source = f"{'#' * level} Overview"
                    rows, _ = render_markdown_line(source, 40, [], [], light=light)
                    rgb = palette[min(level - 1, 2)]
                    self.assertEqual(rows, [f"\x1b[{attrs};38;2;{rgb}mOverview\x1b[0m"])
                    uncolored, _ = render_markdown_line(source, 40, [], [], False, light=light)
                    self.assertEqual(uncolored, ["Overview"])

    def test_light_accent_colors_remain_readable_on_latte_and_white_backgrounds(self):
        def luminance(rgb):
            channels = [channel / 255 for channel in rgb]
            linear = [
                channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
                for channel in channels
            ]
            return sum(
                channel * weight for channel, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True)
            )

        for level in range(1, 7):
            rows, _ = render_markdown_line(f"{'#' * level} Heading", 40, [], [], light=True)
            fragments = to_formatted_text(ANSI(rows[0]))
            foreground = next(token[1:] for token in fragments[0][0].split() if token.startswith("#"))
            rgb = tuple(int(foreground[index:index + 2], 16) for index in (0, 2, 4))
            for background in ((239, 241, 245), (255, 255, 255)):
                with self.subTest(level=level, background=background):
                    contrast = (luminance(background) + 0.05) / (luminance(rgb) + 0.05)
                    self.assertGreaterEqual(contrast, 4.5)

    def test_heading_colors_preserve_inline_emphasis_and_code(self):
        for light, red in ((False, "174"), (True, "124")):
            with self.subTest(light=light):
                rows, _ = render_markdown_line(
                    "## Plan **urgent** and `config.py`", 80, [], [], light=light,
                )
                rendered = "\n".join(rows)
                self.assertIn(f"\x1b[1;38;5;{red}murgent\x1b[0m", rendered)
                self.assertIn("\x1b[1;36mconfig.py\x1b[0m", rendered)
                self.assertEqual(plain(rendered), "Plan urgent and config.py")

    def test_tables_use_accent_headers_muted_borders_and_uncolored_body(self):
        source = ["| Name | Mode |", "| :--- | ---: |", "| alpha | **red** `code` |"]
        for light, rgb, red in (
            (False, "249;226;175", "174"),
            (True, "153;98;20", "124"),
        ):
            with self.subTest(light=light):
                rows = render_table(source, 50, light=light)
                rendered = "\n".join(rows)
                self.assertIn(f"\x1b[1;38;2;{rgb}mName\x1b[0m", rendered)
                self.assertIn(f"\x1b[1;38;2;{rgb}mMode\x1b[0m", rendered)
                self.assertTrue(rows[0].startswith("\x1b[2m╭"))
                self.assertIn("│\x1b[0m alpha ", rendered)
                self.assertIn(f"\x1b[1;38;5;{red}mred\x1b[0m", rendered)
                self.assertIn("\x1b[36mcode\x1b[0m", rendered)
                self.assertEqual([plain(row) for row in rows], render_table(source, 50, False))

    def test_table_accent_survives_stacked_layout_and_header_only_tables(self):
        source = ["| A | B |", "| --- | --- |", "| one | two |", "| end | last |"]
        for light, rgb in ((False, "249;226;175"), (True, "153;98;20")):
            with self.subTest(light=light):
                rows = render_table(source, 8, light=light)
                self.assertEqual(rows[0], f"\x1b[1;38;2;{rgb}mA\x1b[0m: one")
                self.assertEqual(rows[1], f"\x1b[1;38;2;{rgb}mB\x1b[0m: two")
                self.assertIn("\x1b[2m────────\x1b[0m", rows)
                self.assertEqual([plain(row) for row in rows], render_table(source, 8, False))
                header_only = render_table(source[:2], 8, light=light)
                self.assertEqual(header_only, [
                    f"\x1b[1;38;2;{rgb}mA\x1b[0m",
                    f"\x1b[1;38;2;{rgb}mB\x1b[0m",
                ])

    def test_theme_does_not_change_wrapping_alignment_or_streaming(self):
        source = (
            "# A wrapped heading with 日本語\n"
            "## Another heading\n"
            "### A small heading\n"
            "| Name | Count |\n"
            "| :--- | ---: |\n"
            "| 日本語 words to wrap | 123 |\n"
            "| **strong** | 4 |\n"
        )
        for light in (False, True):
            for width in (12, 24, 60):
                with self.subTest(light=light, width=width):
                    batch = StreamCell(width, "•", markdown=True, light=light)
                    expected = batch.push(source) + batch.finish()
                    streamed = StreamCell(width, "•", markdown=True, light=light)
                    actual = []
                    for char in source:
                        actual.extend(streamed.push(char))
                        for row in streamed.tail():
                            self.assertLessEqual(get_cwidth(plain(row)), width)
                    actual.extend(streamed.finish())
                    self.assertEqual(actual, expected)
                    uncolored = StreamCell(width, "•", color=False, markdown=True, light=light)
                    self.assertEqual(
                        [plain(row) for row in actual], uncolored.push(source) + uncolored.finish(),
                    )
