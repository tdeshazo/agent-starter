import unittest
from unittest.mock import patch

from examples.calculator.__main__ import main
from examples.calculator.agent import CALCULATOR_SYSTEM_PROMPT, calculate, create_calculator_agent
from simple_agent.agent import create_agent


class CalculatorExampleTests(unittest.TestCase):
    def test_calculate_evaluates_arithmetic(self):
        for expression, expected in (
            ("37 * 19", "703"),
            (" (12.5 + 7.5) * 3 ", "60.0"),
            ("-5 + 2 ** 3", "3"),
            ("+17 // 5 + 17 % 5", "5"),
            ("17 / 5", "3.4"),
        ):
            with self.subTest(expression=expression):
                self.assertEqual(calculate(expression), expected)

    def test_calculate_rejects_unsupported_and_unbounded_arithmetic(self):
        for expression in (
            "",
            "2 +",
            "1 / 0",
            "True + 1",
            "'a' * 10",
            "abs(-2)",
            "(1).__class__",
            "1e309",
            "1e308 * 10",
            "(-1) ** 0.5",
            "9 ** 9 ** 9",
            "(2 ** 1000) ** 3",
            "1 + " * 21 + "1",
            " " * 256 + "1",
        ):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                calculate(expression)

    def test_calculator_factory_is_opt_in(self):
        calculator = create_calculator_agent()
        self.assertEqual(calculator.system_prompt, CALCULATOR_SYSTEM_PROMPT)
        calculator_names = [spec["name"] for spec in calculator.tool_registry.get_all_tool_specs()]
        self.assertEqual(calculator_names, ["calculate"])
        default_names = {spec["name"] for spec in create_agent().tool_registry.get_all_tool_specs()}
        self.assertNotIn("calculate", default_names)

    def test_module_entry_point_sends_prompt_to_calculator_agent(self):
        with patch("examples.calculator.__main__.create_calculator_agent") as factory:
            main(["What is 37 times 19?"])
        factory.assert_called_once_with()
        factory.return_value.assert_called_once_with("What is 37 times 19?")
