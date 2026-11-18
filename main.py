"""Command-line interface for the local Gemma agent."""
import argparse

from simple_agent import create_agent
from simple_agent.repl import USER_COLOR, USER_LABEL, ReplOutput, Turn, repl_input


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
    read_prompt = repl_input()
    print("Gemma 4 E4B — /quit to exit, /reset to clear history, Alt+Enter for a newline.")
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
        if prompt == "/quit":
            break
        if prompt == "/reset":
            agent = create_agent()
            output = ReplOutput(agent)
        else:
            output.respond(agent, prompt)
            print()


if __name__ == "__main__":
    main()
