"""Expose built-in agent tools and their default registration order."""

from .clock import current_time
from .workspace import read_file, search_text
from .workspace_text import MAX_FILE_BYTES

DEFAULT_TOOLS = (current_time, read_file, search_text)

__all__ = ["DEFAULT_TOOLS", "MAX_FILE_BYTES", "current_time", "read_file", "search_text"]
