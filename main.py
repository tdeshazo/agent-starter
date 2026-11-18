"""Command-line interface for the local Gemma agent."""
import argparse

from simple_agent import create_agent
from simple_agent.repl import USER_COLOR, USER_LABEL, ReplOutput, Turn, repl_session


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", nargs="?", help="Omit for an interactive conversation")
    args = parser.parse_args()
    agent = create_agent()
    if args.prompt:
        agent(args.prompt)
        print()
        return
    output = ReplOutput(agent)
    session = repl_session()
    read_prompt = session.prompt if session is not None else input
    terminal = session.app.input if session is not None else None
    banner = "Gemma 4 E4B — /exit to exit, /clear to clear history, Alt+Enter for a newline."
    if terminal is not None:
        banner += " Esc stops a response."
    print(banner)
    while True:
        try:
            entered = read_prompt()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        prompt = entered.strip()
        if not prompt:
            continue
        user_turn = Turn(USER_LABEL, USER_COLOR)
        user_turn.write(entered)
        user_turn.finish()
        if prompt == "/exit":
            break
        if prompt == "/clear":
            agent = create_agent()
            output = ReplOutput(agent)
        else:
            try:
                output.respond(agent, prompt, terminal)
            except KeyboardInterrupt:
                break
            print()


if __name__ == "__main__":
    main()
