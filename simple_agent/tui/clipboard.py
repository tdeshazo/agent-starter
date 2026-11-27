"""Copy selected text using a native clipboard or a bounded OSC 52 request."""
import asyncio
import base64
import os
import shutil
import subprocess
import sys

from prompt_toolkit.output import Output
from prompt_toolkit.output.vt100 import Vt100_Output

NATIVE_TIMEOUT = 1.0
OSC52_MAX_RAW_BYTES = 100_000


def _native_commands() -> list[tuple[list[str], str]]:
    """Return clipboard writers appropriate for this session and their encodings."""
    if sys.platform == "darwin":
        return [(["pbcopy"], "utf-8")]
    if sys.platform == "win32":
        return [(["clip.exe"], "utf-16")]
    commands = []
    if os.getenv("WAYLAND_DISPLAY"):
        commands.append((["wl-copy", "--type", "text/plain;charset=utf-8"], "utf-8"))
    if os.getenv("DISPLAY"):
        commands.extend([
            (["xclip", "-selection", "clipboard"], "utf-8"),
            (["xsel", "--clipboard", "--input"], "utf-8"),
        ])
    if os.getenv("WSL_DISTRO_NAME") or os.getenv("WSL_INTEROP"):
        # Include a BOM so clip.exe recognizes Unicode instead of its ANSI page.
        commands.append((["clip.exe"], "utf-16"))
    return commands


def _copy_native(text: str) -> bool:
    for command, encoding in _native_commands():
        executable = shutil.which(command[0])
        if executable is None:
            continue
        try:
            subprocess.run(
                [executable, *command[1:]],
                input=text.encode(encoding),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=NATIVE_TIMEOUT,
                check=True,
            )
        except (OSError, subprocess.SubprocessError, UnicodeError):
            continue
        return True
    return False


def _terminal_clipboard_available(output: Output) -> bool:
    # Plain/Dummy outputs either escape or discard control sequences. Never
    # report clipboard delivery for those, or write an OSC request to a pipe.
    if not isinstance(output, Vt100_Output) or os.getenv("TERM") == "dumb":
        return False
    try:
        return output.stdout.isatty()
    except (AttributeError, OSError):
        return False


async def copy_text(text: str, output: Output) -> str:
    """Copy without blocking the UI, returning an honest user-facing status.

    OSC 52 is a best-effort request: the terminal may require permission or
    disable clipboard access. Its status deliberately does not claim success.
    """
    if not text:
        return "Select text to copy."
    if await asyncio.to_thread(_copy_native, text):
        return "Copied selection."
    if not _terminal_clipboard_available(output):
        return "Clipboard unavailable. Use your terminal's copy shortcut."
    try:
        payload = text.encode("utf-8")
    except UnicodeError:
        return "Could not encode selection for the clipboard."
    if len(payload) > OSC52_MAX_RAW_BYTES:
        return "Selection is too large for terminal copying; use your terminal's copy shortcut."
    encoded = base64.b64encode(payload).decode("ascii")
    sequence = f"\x1b]52;c;{encoded}\x07"
    if os.getenv("TMUX"):
        sequence = "\x1bPtmux;" + sequence.replace("\x1b", "\x1b\x1b") + "\x1b\\"
    try:
        output.write_raw(sequence)
        output.flush()
    except (OSError, ValueError):
        return "Could not copy selection. Use your terminal's copy shortcut."
    return "Sent selection to terminal clipboard."
