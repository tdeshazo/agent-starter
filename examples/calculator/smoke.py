"""Verify one calculator tool turn against the configured local model."""

import argparse
import ast
import re
from collections.abc import Iterable, Sequence

from simple_agent.conversation import ConversationEvent, InvocationError, TextDelta, ToolCall, ToolResult
from simple_agent.strands_backend import StrandsBackend, invocation_error

from .agent import _MAX_EXPRESSION_LENGTH, create_calculator_agent

_LEFT, _RIGHT = 37, 19
EXPRESSION = f"{_LEFT} * {_RIGHT}"
EXPECTED = _LEFT * _RIGHT
PROMPT = f"Use the calculate tool to evaluate {EXPRESSION}. Reply with only the resulting number."
_RESULT_NUMBER = rf"{EXPECTED}(?:\.0+)?"


class SmokeFailure(RuntimeError):
    """The turn omitted a required calculator interaction."""


def _used_requested_expression(arguments: object) -> bool:
    if not isinstance(arguments, dict) or not isinstance(expression := arguments.get("expression"), str):
        return False
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        return False
    try:
        node = ast.parse(expression.strip(), mode="eval").body
    except (SyntaxError, RecursionError, UnicodeError):
        return False
    match node:
        case ast.BinOp(left=ast.Constant(value=left), op=ast.Mult(), right=ast.Constant(value=right)):
            return (left, right) in ((_LEFT, _RIGHT), (_RIGHT, _LEFT))
        case _:
            return False


def _normalize_reply(reply: str) -> str:
    reply = reply.strip().removesuffix(".").rstrip()
    for marker in ("```", "`", "**", "__", "*", "_"):
        if reply.startswith(marker) and reply.endswith(marker):
            return reply[len(marker):-len(marker)].strip().removesuffix(".")
    return reply


def verify_smoke(events: Iterable[ConversationEvent]) -> None:
    saw_calculate = False
    matching_calls: set[str] = set()
    result_verified = False
    answer_chunks: list[str] = []

    for event in events:
        if isinstance(event, (ToolCall, ToolResult)):
            # Each tool cycle starts a new candidate for the final reply.
            answer_chunks.clear()
        if isinstance(event, ToolCall) and event.name == "calculate" and event.id:
            saw_calculate = True
            if _used_requested_expression(event.arguments):
                matching_calls.add(event.id)
        elif isinstance(event, ToolResult) and event.id in matching_calls and not event.failed:
            if len(event.parts) == 1 and re.fullmatch(_RESULT_NUMBER, event.parts[0].strip()):
                result_verified = True
        elif isinstance(event, TextDelta) and not event.reasoning:
            answer_chunks.append(event.text)

    if not saw_calculate:
        raise SmokeFailure("The model did not call calculate.")
    if not matching_calls:
        raise SmokeFailure(f"The model did not use calculate for {EXPRESSION}.")
    if not result_verified:
        raise SmokeFailure(f"No successful calculate result matched {EXPECTED}.")
    if not re.fullmatch(rf"\+?{_RESULT_NUMBER}", _normalize_reply("".join(answer_chunks))):
        raise SmokeFailure(f"The final reply did not give {EXPECTED} as its sole answer.")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m examples.calculator.smoke", description=__doc__)
    parser.parse_args(argv)
    events: list[ConversationEvent] = []
    try:
        backend = StrandsBackend(create_calculator_agent())
        backend.observe(events.append)
        backend.invoke(PROMPT)
        verify_smoke(events)
    except KeyboardInterrupt:
        parser.exit(130, "\nInterrupted.\n")
    except SmokeFailure as error:
        parser.exit(1, f"Calculator smoke failed. {error}\n")
    except Exception as error:
        problem = error if isinstance(error, InvocationError) else invocation_error(error)
        parser.exit(
            1,
            f"Calculator smoke failed. {problem}\n"
            "Check that the model server is running and AGENT_BASE_URL or AGENT_PORT is correct.\n",
        )

    print(f"Calculator smoke passed. The reply confirmed calculate returned {EXPECTED} for {EXPRESSION}.")


if __name__ == "__main__":
    main()
