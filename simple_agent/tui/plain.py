"""Run the line-oriented terminal interface for pipes and dumb terminals."""
import shutil
import time
from collections.abc import Callable

from ..conversation import Conversation, InvocationError
from ..preferences import PET_NAMES, UserPreferences
from .commands import command_output, parse_slash_command, reasoning_command
from .session import session_info
from .terminal import use_color, write_rows
from .transcript import Transcript


def run_plain(
    conversation: Conversation,
    preferences: UserPreferences,
    read: Callable[[], str] = input,
) -> None:
    """Line-oriented fallback for pipes and dumb terminals."""
    color = use_color()
    pet = preferences.pet()
    transcript = Transcript(
        write_rows,
        lambda: shutil.get_terminal_size().columns,
        color,
    )
    conversation.observe(transcript)
    transcript.header(pet=pet, **session_info(conversation.details()))
    while True:
        try:
            entered = read()
        except (EOFError, KeyboardInterrupt):
            break
        prompt = entered.strip()
        if not prompt:
            continue
        cmd = parse_slash_command(prompt, interactive=False)
        if cmd is not None:
            if cmd.error:
                transcript.error(cmd.error)
            elif cmd.name == "/exit":
                break
            elif cmd.name == "/settings":
                transcript.info("Open the full-screen interface to edit agent settings.")
            elif cmd.name == "/clear":
                try:
                    conversation.reset()
                except InvocationError as error:
                    transcript.error(str(error))
                else:
                    transcript.info("Started a new conversation.")
            elif cmd.name == "/reasoning":
                transcript.info(reasoning_command(cmd, conversation))
            elif cmd.name == "/pet":
                if cmd.arg is None:
                    choices = ", ".join(PET_NAMES)
                    transcript.info(f"Current pet: {pet}. Choose from: {choices} (use /pet <name>).")
                else:
                    try:
                        pet = preferences.select_pet(cmd.arg)
                    except ValueError as error:
                        transcript.error(str(error))
                    except OSError as error:
                        transcript.error(f"Could not save pet preference: {error}")
                    else:
                        transcript.info(f"Selected pet: {pet}.")
            elif result := command_output(cmd.name, conversation):
                transcript.info(result)
            continue
        transcript.user(entered)
        started = time.monotonic()
        try:
            conversation.invoke(prompt)
        except KeyboardInterrupt:
            transcript.end_turn(time.monotonic() - started, stopped=True)
            break
        except InvocationError as error:
            transcript.error(str(error))
        transcript.end_turn(time.monotonic() - started)
