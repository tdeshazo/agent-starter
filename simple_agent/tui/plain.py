"""Run the line-oriented terminal interface for pipes and dumb terminals."""
from pathlib import Path
import shutil
import time
from collections.abc import Callable

from .commands import command_output, parse_pet_command
from .pets import PET_NAMES, load_pet, normalize_pet, save_pet
from .session import conversation_turn, session_info
from .terminal import use_color, write_rows
from .transcript import Transcript


def run_plain(
    agent_factory: Callable[[], object],
    agent=None,
    read: Callable[[], str] = input,
    *,
    config_path: Path | None = None,
) -> None:
    """Line-oriented fallback for pipes and dumb terminals."""
    color = use_color()
    pet = load_pet(config_path)
    transcript = Transcript(
        write_rows,
        lambda: shutil.get_terminal_size().columns,
        color,
    )
    agent = agent if agent is not None else agent_factory()
    agent.callback_handler = transcript
    transcript.header(pet=pet, **session_info(agent))
    while True:
        try:
            entered = read()
        except (EOFError, KeyboardInterrupt):
            break
        prompt = entered.strip()
        if not prompt:
            continue
        if prompt == "/exit":
            break
        if prompt == "/clear":
            agent = agent_factory()
            agent.callback_handler = transcript
            transcript.info("Started a new conversation.")
            continue
        is_pet, pet_arg = parse_pet_command(prompt)
        if is_pet:
            if pet_arg is None:
                choices = ", ".join(PET_NAMES)
                transcript.info(f"Current pet: {pet}. Choose from: {choices} (use /pet <name>).")
            else:
                chosen = normalize_pet(pet_arg)
                if chosen is None:
                    choices = ", ".join(PET_NAMES)
                    transcript.error(f"Unknown pet {pet_arg!r}. Choose from: {choices}.")
                else:
                    try:
                        save_pet(chosen, config_path)
                    except OSError as error:
                        transcript.error(f"Could not save pet preference: {error}")
                    else:
                        pet = chosen
                        transcript.info(f"Selected pet: {chosen}.")
            continue
        if result := command_output(prompt, agent):
            transcript.info(result)
            continue
        transcript.user(entered)
        started = time.monotonic()
        try:
            with conversation_turn(agent.messages):
                agent(prompt)
        except KeyboardInterrupt:
            transcript.end_turn(time.monotonic() - started, stopped=True)
            break
        except Exception as error:
            transcript.invocation_failed(error)
        transcript.end_turn(time.monotonic() - started)
