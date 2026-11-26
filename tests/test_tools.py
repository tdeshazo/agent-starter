import os
import tempfile
import unittest
from pathlib import Path

from simple_agent.tools import DEFAULT_TOOLS, MAX_FILE_BYTES, current_time, read_file, search_text


class ToolTests(unittest.TestCase):
    def test_current_time_returns_iso_timestamp_and_rejects_bad_timezone(self):
        stamp = current_time("America/New_York")
        self.assertIn("T", stamp)
        with self.assertRaises(Exception):
            current_time("Not/A_Timezone")

    def test_read_file_reads_workspace_files_and_enforces_size_limit(self):
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                root = Path(tmp).resolve()
                (root / "notes.txt").write_text("hello world\n", encoding="utf-8")
                (root / ".env.example").write_text("PORT=8088\n", encoding="utf-8")
                (root / "big.txt").write_bytes(b"x" * (MAX_FILE_BYTES + 1))

                self.assertEqual(read_file("notes.txt"), "hello world\n")
                self.assertEqual(read_file(str(root / "notes.txt")), "hello world\n")
                self.assertEqual(read_file(".env.example"), "PORT=8088\n")

                with self.assertRaisesRegex(ValueError, "read limit"):
                    read_file("big.txt")
            finally:
                os.chdir(original_cwd)

    def test_read_file_blocks_outside_paths_symlinks_sensitive_dotfiles_and_special_files(self):
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as outer:
            outside = Path(outer) / "secret.txt"
            outside.write_text("outside secret", encoding="utf-8")
            workspace = Path(outer) / "workspace"
            workspace.mkdir()
            (workspace / ".env").write_text("API_KEY=secret\n", encoding="utf-8")
            (workspace / ".env.local").write_text("LOCAL_SECRET=1\n", encoding="utf-8")
            git_dir = workspace / ".git"
            git_dir.mkdir()
            (git_dir / "config").write_text("[remote]\n", encoding="utf-8")
            (workspace / "sub").mkdir()
            (workspace / "sub" / ".env").write_text("NESTED=1\n", encoding="utf-8")
            (workspace / "escape_link.txt").symlink_to(outside)
            (workspace / "env_link.txt").symlink_to(workspace / ".env")
            fifo = workspace / "pipe.fifo"
            os.mkfifo(fifo)

            os.chdir(workspace)
            try:
                for blocked_outside in ("../secret.txt", str(outside), "escape_link.txt"):
                    with self.assertRaisesRegex(ValueError, "outside the working directory"):
                        read_file(blocked_outside)

                for sensitive in (".env", ".env.local", "sub/.env", ".git/config", "env_link.txt"):
                    with self.assertRaisesRegex(ValueError, "sensitive file"):
                        read_file(sensitive)

                for non_regular in (".", "sub", "pipe.fifo"):
                    with self.assertRaisesRegex(ValueError, "regular file"):
                        read_file(non_regular)

                for blocked in (
                    "../secret.txt", "escape_link.txt", ".env", "env_link.txt", ".git/config", "pipe.fifo"
                ):
                    with self.subTest(path=blocked), self.assertRaises(ValueError):
                        read_file(blocked, 1, 1)
            finally:
                os.chdir(original_cwd)


class WorkspaceSearchTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.addCleanup(os.chdir, Path.cwd())
        os.chdir(self.root)

    def test_search_text_finds_literal_case_sensitive_matches_recursively(self):
        self.assertIn(search_text, DEFAULT_TOOLS)
        (self.root / "nested").mkdir()
        (self.root / "nested" / "notes.txt").write_text(
            "[a+b].\ninside [a+b]. repeated [a+b]. here\ninside [A+B]. here\ninside abX here\n",
            encoding="utf-8",
        )
        (self.root / "root.txt").write_text("outside [a+b]. here", encoding="utf-8")

        result = search_text(" [a+b]. ")

        self.assertCountEqual(
            [line.split(":", 2)[:2] for line in result.splitlines()],
            [["nested/notes.txt", "2"], ["root.txt", "1"]],
        )
        self.assertIn("inside [a+b]. repeated [a+b]. here", result)
        self.assertEqual(search_text(" [a+b]. "), result)
        self.assertEqual(search_text("missing"), "No matches.")

    def test_search_text_rejects_blank_or_multiline_queries(self):
        for query in ("", " \t", "first\nsecond", "first\rsecond"):
            with self.subTest(query=query), self.assertRaises(ValueError):
                search_text(query)

    def test_search_text_keeps_line_breaks_in_paths_distinct_and_on_one_row(self):
        filenames = ("notes\nfile.txt", r"notes\nfile.txt", "notes\u2028file.txt")
        for filename in filenames:
            (self.root / filename).write_text("needle\n", encoding="utf-8")

        rows = search_text("needle").splitlines()

        self.assertEqual(len(rows), len(filenames))
        paths = set()
        for row in rows:
            path, separator, snippet = row.partition(":1:")
            self.assertTrue(path)
            self.assertTrue(separator)
            self.assertEqual(snippet.strip(), "needle")
            paths.add(path)
        self.assertEqual(len(paths), len(filenames))

    def test_search_text_skips_excluded_paths_and_non_text_files(self):
        for directory in ("nested/.git", "nested/.venv", "nested/__pycache__", "nested/node_modules"):
            path = self.root / directory
            path.mkdir(parents=True)
            (path / "excluded.txt").write_text("needle\n", encoding="utf-8")

        for name in (".env", ".env.local", ".env.example", ".env.sample", ".env.template"):
            (self.root / "nested" / name).write_text("needle\n", encoding="utf-8")

        (self.root / "nul.txt").write_bytes(b"needle\n\x00")
        (self.root / "bad-utf8.txt").write_bytes(b"needle\n\xff")
        (self.root / "oversized.txt").write_bytes(b"needle\n" + b"x" * (1024 * 1024))
        (self.root / "file-link.txt").symlink_to(self.root / "nested" / ".env.example")
        (self.root / "dir-link").symlink_to(self.root / "nested", target_is_directory=True)
        os.mkfifo(self.root / "pipe.fifo")

        outside = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (outside / "secret.txt").write_text("needle\n", encoding="utf-8")
        (self.root / "outside-link").symlink_to(outside, target_is_directory=True)

        lines = search_text("needle").splitlines()
        notices = [line for line in lines if "incomplete" in line.lower()]

        self.assertCountEqual(
            [line.split(":", 2)[0] for line in lines if line not in notices],
            ["nested/.env.example", "nested/.env.sample", "nested/.env.template"],
        )
        self.assertTrue(notices)

    def test_search_text_reports_incomplete_search_at_depth_limit(self):
        deep_directory = self.root / "/".join(["nested"] * 40)
        deep_directory.mkdir(parents=True)
        (deep_directory / "deep.txt").write_text("needle\n", encoding="utf-8")
        (self.root / "visible.txt").write_text("needle\n", encoding="utf-8")

        result = search_text("needle")

        self.assertRegex(result, r"(?m)^visible\.txt:1:\s*needle")
        self.assertNotIn("deep.txt:", result)
        self.assertIn("incomplete", result.lower())

    def test_search_text_caps_rows_and_signals_truncation(self):
        (self.root / "many.txt").write_text("needle\n" * 25, encoding="utf-8")

        lines = search_text("needle").splitlines()
        rows = [line for line in lines if line.startswith("many.txt:")]
        notices = [line for line in lines if line not in rows and line.strip()]

        self.assertTrue(rows)
        self.assertLessEqual(len(rows), 20)
        self.assertTrue(notices)

    def test_search_text_keeps_matches_visible_within_byte_limit(self):
        long_line = "🦉" * 1500 + "needle" + "🦉" * 1500 + "\n"
        (self.root / "wide.txt").write_text(long_line * 20, encoding="utf-8")

        result = search_text("needle")
        rows = [line for line in result.splitlines() if line.startswith("wide.txt:")]

        self.assertLessEqual(len(result.encode("utf-8")), MAX_FILE_BYTES)
        self.assertTrue(rows)
        for row in rows:
            self.assertIn("needle", row)

    def test_search_text_omits_a_row_when_the_literal_cannot_fit(self):
        filename = "x" * 192
        query = "🦉"
        (self.root / filename).write_text("p" + (query + "\n") * 20, encoding="utf-8")

        result = search_text(query)
        rows = [line for line in result.splitlines() if line.startswith(filename + ":")]

        self.assertTrue(rows)
        self.assertLess(len(rows), 20)
        self.assertLessEqual(len(result.encode("utf-8")), MAX_FILE_BYTES)
        self.assertIn("Search incomplete", result)
        for row in rows:
            self.assertIn(query, row)

    def test_search_text_can_locate_a_range_past_the_whole_file_read_limit(self):
        (self.root / "notes.txt").write_bytes(b"intro\r\n" * 700 + b"needle\r\nlast line")

        with self.assertRaises(ValueError):
            read_file("notes.txt")
        self.assertRegex(search_text("needle"), r"^notes\.txt:701:\s*needle")
        self.assertEqual(read_file("notes.txt", 701, 701), "needle\r\n")
        self.assertEqual(read_file("notes.txt", 701, 800), "needle\r\nlast line")
        self.assertEqual(read_file("notes.txt", 703, 800), "")

    def test_read_file_requires_positive_ordered_range_with_both_endpoints(self):
        (self.root / "notes.txt").write_text("first\nsecond\n", encoding="utf-8")

        for start, end in ((1, None), (None, 2), (0, 1), (-1, 1), (1, 0), (2, 1)):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                read_file("notes.txt", start, end)

    def test_read_file_traverses_search_only_ancestor_for_both_read_modes(self):
        restricted = self.root / "restricted"
        restricted.mkdir(mode=0o700)
        (restricted / "nested").mkdir()
        relative_path = "restricted/nested/notes.txt"
        (self.root / relative_path).write_text("first\nsecond\n", encoding="utf-8")

        try:
            restricted.chmod(0o111)
        except (NotImplementedError, PermissionError):
            self.skipTest("Cannot set directory permissions on this filesystem")
        self.addCleanup(restricted.chmod, 0o700)
        if os.access(restricted, os.R_OK) or not os.access(restricted, os.X_OK):
            self.skipTest("Search-only directory permissions are unavailable")

        self.assertEqual(read_file(relative_path), "first\nsecond\n")
        self.assertEqual(read_file(relative_path, start_line=2, end_line=2), "second\n")

    def test_read_file_enforces_range_output_and_input_byte_limits(self):
        line_at_limit = "é" * (MAX_FILE_BYTES // 2 - 1) + "\r\n"
        (self.root / "wide.txt").write_bytes(line_at_limit.encode("utf-8") + b"x")
        file_at_limit = self.root / "large.txt"
        first_line = b"first\n"
        file_at_limit.write_bytes(first_line + b"x" * (1024 * 1024 - len(first_line)))

        self.assertEqual(read_file("wide.txt", 1, 1), line_at_limit)
        with self.assertRaises(ValueError):
            read_file("wide.txt", 1, 2)

        self.assertEqual(read_file("large.txt", 1, 1), "first\n")
        with file_at_limit.open("ab") as file:
            file.write(b"x")
        with self.assertRaises(ValueError):
            read_file("large.txt", 1, 1)
