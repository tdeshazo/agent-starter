"""Command-line interface for the local Gemma agent."""
import argparse

from simple_agent import create_agent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", nargs="?", help="Omit for an interactive conversation")
    args = parser.parse_args()
    agent = create_agent()
    if args.prompt:
        agent(args.prompt)
        print()
        return
    print("Gemma 4 E4B — type /quit to exit; /reset to clear history.")
    while True:
        try:
            prompt = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if prompt == "/quit":
            break
        if prompt == "/reset":
            agent = create_agent()
        elif prompt:
            agent(prompt)
            print()


if __name__ == "__main__":
    main()
