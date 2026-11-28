"""Send one prompt to the calculator agent."""

import argparse
from collections.abc import Sequence

from simple_agent.strands_backend import invocation_error

from .agent import create_calculator_agent


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m examples.calculator", description=__doc__)
    parser.add_argument("prompt", help="A prompt for the calculator agent")
    args = parser.parse_args(argv)
    try:
        create_calculator_agent()(args.prompt)
    except KeyboardInterrupt:
        parser.exit(130, "\nInterrupted.\n")
    except Exception as error:
        parser.exit(1, f"{invocation_error(error)}\n")


if __name__ == "__main__":
    main()
