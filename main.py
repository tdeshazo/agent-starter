"""Command-line interface for the local Gemma agent."""
import argparse

from simple_agent import create_agent
from simple_agent.settings import apply_agent_settings
from simple_agent.tui import PET_NAMES, AgentTui, interactive_terminal, run_plain, save_pet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", nargs="?", help="Omit for an interactive conversation")
    parser.add_argument(
        "--pet",
        choices=PET_NAMES,
        help=f"Select and save the header pet ({', '.join(PET_NAMES)})",
    )
    args = parser.parse_args()
    if args.pet:
        save_pet(args.pet)
    if args.prompt:
        agent = create_agent()
        apply_agent_settings(agent)
        agent(args.prompt)
        print()
    elif interactive_terminal():
        AgentTui(create_agent).run()
    else:
        run_plain(create_agent)


if __name__ == "__main__":
    main()
