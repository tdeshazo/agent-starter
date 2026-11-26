"""Terminal entry points and shared transcript rendering."""

from .app import AgentTui
from .pets import DEFAULT_PET, PET_NAMES, load_pet, pet_rows, save_pet
from .plain import run_plain
from .rendering import StreamCell, header_cell, wrap
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
    "save_pet",
    "session_info",
    "wrap",
]
