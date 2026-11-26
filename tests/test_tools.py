import os
from pathlib import Path
import tempfile
import unittest

from simple_agent.tools import MAX_FILE_BYTES, current_time, read_file


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
            finally:
                os.chdir(original_cwd)
