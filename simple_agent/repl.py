"""Terminal input and output for the interactive agent."""
import os
import re
import shutil
import sys

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.utils import get_cwidth


USER_LABEL = "You>"
USER_COLOR = "1;36"
AGENT_COLOR = "1;35"
TURN_TOKENS = re.compile(r"\n|[^\S\n]+|\S+")


def styled(text: str, color: str) -> str:
    if sys.stdout.isatty() and not os.getenv("NO_COLOR") and os.getenv("TERM") != "dumb":
        return f"\x1b[{color}m{text}\x1b[0m"
    return text


class Turn:
    """Write a labeled turn, holding partial words until they can be wrapped."""

    def __init__(self, label: str, color: str):
        self.indent = " " * (get_cwidth(label) + 1)
        self.width = shutil.get_terminal_size().columns
        self.column = len(self.indent)
        self.prefix = ""
        self.space = ""
        self.partial_word = ""
        print(styled(label, color), end=" ", flush=True)

    def write(self, chunk: str) -> None:
        text = self.partial_word + chunk
        end = 0
        for match in TURN_TOKENS.finditer(text):
            token = match[0]
            if match.end() == len(text) and not token.isspace():
                break
            end = match.end()
            if token == "\n":
                self._newline()
            elif token.isspace():
                self.space += token.replace("\t", "    ").replace("\r", "")
            else:
                self._word(token)
        self.partial_word = text[end:]

    def _word(self, word: str, display: str | None = None) -> None:
        word_width = get_cwidth(word)
        space_width = get_cwidth(self.space)
        if self.column > len(self.indent) and self.column + space_width + word_width > self.width:
            self._newline()
            space_width = 0
        print(self.prefix + self.space + (display or word), end="", flush=True)
        self.column += space_width + word_width
        self.prefix = ""
        self.space = ""

    def _newline(self) -> None:
        print(flush=True)
        self.column = len(self.indent)
        self.prefix = self.indent
        self.space = ""

    def finish(self) -> None:
        if self.partial_word:
            self._word(self.partial_word)
            self.partial_word = ""
        if not self.prefix:
            self._newline()

    def tool(self, label: str, name: str) -> None:
        if self.partial_word or self.column > len(self.indent):
            self.finish()
        self.space = ""
        self._word(label, styled(label, "1;33"))
        self.write(" " + name)
        self.finish()


class ReplOutput:
    """Render Strands events within the current agent turn."""

    def __init__(self, agent):
        model_id = agent.model.get_config()["model_id"]
        self.label = f"{model_id.rsplit('/', 1)[-1].split('-', 1)[0].capitalize()}>"
        self.tool_count = 0
        self.turn: Turn
        agent.callback_handler = self

    def respond(self, agent, prompt: str) -> None:
        self.turn = Turn(self.label, AGENT_COLOR)
        try:
            agent(prompt)
        finally:
            self.turn.finish()

    def __call__(self, **kwargs):
        for key in ("reasoningText", "data"):
            if chunk := kwargs.get(key):
                self.turn.write(chunk)

        start = kwargs.get("event", {}).get("contentBlockStart", {}).get("start", {})
        tool_use = start.get("toolUse")
        if tool_use:
            self.tool_count += 1
            self.turn.tool(f"Tool #{self.tool_count}:", tool_use["name"])


def repl_input():
    if not (sys.stdin.isatty() and sys.stdout.isatty()) or os.getenv("TERM") == "dumb":
        return input

    bindings = KeyBindings()

    @bindings.add("escape", "enter")
    def insert_newline(event):
        event.current_buffer.insert_text("\n")

    session = PromptSession(
        ANSI(f"{styled(USER_LABEL, USER_COLOR)} "),
        prompt_continuation=" " * (len(USER_LABEL) + 1),
        erase_when_done=True,
        key_bindings=bindings,
        wrap_lines=False,
    )
    return session.prompt
