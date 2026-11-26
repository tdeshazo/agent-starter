"""Command-line interface for the local Gemma agent."""
import argparse

from simple_agent import create_agent
from simple_agent.tui import AgentTui, interactive_terminal, run_plain


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", nargs="?", help="Omit for an interactive conversation")
    args = parser.parse_args()
    if args.prompt:
        create_agent()(args.prompt)
        print()
    elif interactive_terminal():
        AgentTui(create_agent).run()
    else:
        run_plain(create_agent)


if __name__ == "__main__":
    main()
