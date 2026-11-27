"""Filesystem access and scan limits for local workspace tools."""

import os
from collections.abc import Iterator
from contextlib import closing, contextmanager
from io import BufferedReader
from pathlib import Path
from stat import S_ISREG


MAX_CANDIDATE_FILE_BYTES = 1024 * 1024
MAX_SEARCH_ENTRIES = 10_000
MAX_SEARCH_READ_BYTES = 32 * 1024 * 1024
MAX_SEARCH_DEPTH = 32
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


def read_workspace_bytes(path: str, limit: int) -> bytes:
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

    with _open_workspace_file(rel_parts, path) as file:
        contents = file.read(limit + 1)
    if len(contents) > limit:
        raise ValueError(f"File exceeds the {limit}-byte read limit.")
    return contents


class WorkspaceScan:
    """A single bounded scan and its completion status."""

    def __init__(self):
        self.incomplete = False
        self._entries_left = MAX_SEARCH_ENTRIES

    def _candidates(self, directory_fd: int, path: str, depth: int) -> Iterator[tuple[int, str, str]]:
        children = []
        with os.scandir(directory_fd) as entries:
            for entry in entries:
                if self._entries_left == 0:
                    self.incomplete = True
                    return
                self._entries_left -= 1
                if entry.name in SEARCH_SKIP_NAMES or _is_sensitive_path((entry.name,)):
                    continue
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                    if is_dir or entry.is_file(follow_symlinks=False):
                        children.append((entry.name + "/" if is_dir else entry.name, is_dir))
                except OSError:
                    self.incomplete = True

        for name, is_dir in sorted(children):
            relative = path + name
            if not is_dir:
                yield directory_fd, name, relative
                continue
            if depth == MAX_SEARCH_DEPTH or self._entries_left == 0:
                self.incomplete = True
                continue
            try:
                child_fd = os.open(name[:-1], DIRECTORY_READ_FLAGS, dir_fd=directory_fd)
                try:
                    yield from self._candidates(child_fd, relative, depth + 1)
                finally:
                    os.close(child_fd)
            except OSError:
                self.incomplete = True

    def files(self) -> Iterator[tuple[str, bytes]]:
        read_left = MAX_SEARCH_READ_BYTES
        try:
            root_fd = os.open(".", DIRECTORY_READ_FLAGS)
        except OSError:
            self.incomplete = True
            return
        try:
            with closing(self._candidates(root_fd, "", 0)) as files:
                for parent_fd, name, path in files:
                    try:
                        with _open_regular_file(parent_fd, name, path) as (file, info):
                            if info.st_size > MAX_CANDIDATE_FILE_BYTES:
                                self.incomplete = True
                                continue
                            limit = min(MAX_CANDIDATE_FILE_BYTES, read_left - 1)
                            if info.st_size > limit:
                                self.incomplete = True
                                break
                            contents = file.read(limit + 1)
                    except (OSError, ValueError):
                        self.incomplete = True
                        continue

                    read_left -= len(contents)
                    if len(contents) > limit:
                        self.incomplete = True
                        if read_left == 0:
                            break
                        continue
                    yield path, contents
        except OSError:
            self.incomplete = True
        finally:
            os.close(root_fd)
