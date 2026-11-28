"""Build a calculator agent with a bounded arithmetic tool."""

import ast
import math
import operator

from strands import Agent, tool

from simple_agent import create_agent

CALCULATOR_SYSTEM_PROMPT = (
    "You are a calculator assistant. Use the calculate tool for every arithmetic request. "
    "Pass a single arithmetic expression using Python syntax, then report the result returned by the tool."
)

_MAX_EXPRESSION_LENGTH = 256
_MAX_AST_NODES = 64
_MAX_INTEGER_BITS = 2048
_MAX_EXPONENT = 1000

_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _check_number(value: object) -> int | float:
    if type(value) is int:
        if value.bit_length() > _MAX_INTEGER_BITS:
            raise ValueError("Integer exceeds the calculator size limit.")
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise ValueError("Only finite real numbers are supported.")


def _evaluate(node: ast.expr) -> int | float:
    if isinstance(node, ast.Constant):
        return _check_number(node.value)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _UNARY_OPERATORS[type(node.op)](_evaluate(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        left = _evaluate(node.left)
        right = _evaluate(node.right)
        if isinstance(node.op, ast.Pow):
            if abs(right) > _MAX_EXPONENT:
                raise ValueError("Exponent exceeds the calculator limit.")
            if isinstance(left, int) and isinstance(right, int) and right > 0:
                # Reject powers whose lower bound already exceeds the bit limit.
                if (left.bit_length() - 1) * right >= _MAX_INTEGER_BITS:
                    raise ValueError("Power exceeds the calculator size limit.")
        return _check_number(_BINARY_OPERATORS[type(node.op)](left, right))
    raise ValueError("Use only numbers, parentheses, and supported arithmetic operators.")


@tool
def calculate(expression: str) -> str:
    """Evaluate arithmetic with integers, floats, and parentheses.

    Supports +, -, *, /, //, %, **, and unary signs.

    Args:
        expression: One arithmetic expression, such as '37 * 19'.
    """
    if not isinstance(expression, str):
        raise ValueError("The expression must be a string.")
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        raise ValueError("Expression exceeds the calculator length limit.")
    expression = expression.strip()
    if not expression:
        raise ValueError("Enter an arithmetic expression.")
    try:
        parsed = ast.parse(expression, mode="eval")
    except (SyntaxError, RecursionError) as error:
        raise ValueError("Invalid arithmetic syntax.") from error
    if sum(1 for _ in ast.walk(parsed)) > _MAX_AST_NODES:
        raise ValueError("Expression exceeds the calculator complexity limit.")
    try:
        return str(_evaluate(parsed.body))
    except ArithmeticError as error:
        raise ValueError(f"Cannot calculate expression: {error}") from error


def create_calculator_agent() -> Agent:
    """Create an agent with the calculator prompt and tool."""
    return create_agent(system_prompt=CALCULATOR_SYSTEM_PROMPT, tools=(calculate,))
