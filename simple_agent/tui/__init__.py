"""Terminal entry points and shared transcript rendering."""

from ..preferences import DEFAULT_PET, PET_NAMES
from ..settings import load_pet, save_pet
from .app import AgentTui
from .pets import pet_rows
from .plain import run_plain
from .rendering import StreamCell, header_cell, sanitize_text, wrap
from .session import session_info
from .terminal import interactive_terminal
from .transcript import Transcript

__all__ = [
    "AgentTui",
    "DEFAULT_PET",
    "PET_NAMES",
    "StreamCell",
    "Transcript",
    "header_cell",
    "interactive_terminal",
    "load_pet",
    "pet_rows",
    "run_plain",
    "sanitize_text",
    "save_pet",
    "session_info",
    "wrap",
]
