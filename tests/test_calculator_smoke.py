import unittest

from examples.calculator.agent import _MAX_EXPRESSION_LENGTH
from examples.calculator.smoke import SmokeFailure, verify_smoke
from simple_agent.conversation import TextDelta, TokenUsage, ToolCall, ToolResult

CALL = ToolCall("calculator-1", "calculate", {"expression": "37 * 19"})
RESULT = ToolResult(CALL.id, ("703",), False)


class CalculatorSmokeTests(unittest.TestCase):
    def test_verifies_matching_call_result_and_streamed_answer(self):
        verify_smoke(
            [
                TextDelta("I'll calculate it."),
                CALL,
                ToolResult(CALL.id, ("703.0",), False),
                TextDelta("**70"),
                TextDelta("3**."),
                TokenUsage({"input": 12}),
            ]
        )

    def test_accepts_parentheses_and_reversed_factors(self):
        call = ToolCall(CALL.id, "calculate", {"expression": "  ((19) * (37))  "})
        verify_smoke([call, RESULT, TextDelta("`703`")])

    def test_rejects_a_missing_or_unrelated_call(self):
        for calls in ([], [ToolCall(CALL.id, "other_tool", {})], [ToolCall("", "calculate", {})]):
            with self.subTest(calls=calls), self.assertRaisesRegex(SmokeFailure, "did not call calculate"):
                verify_smoke([*calls, RESULT, TextDelta("703")])

    def test_rejects_a_different_expression_with_the_same_result(self):
        call = ToolCall(CALL.id, "calculate", {"expression": "703"})
        with self.assertRaisesRegex(SmokeFailure, "did not use calculate"):
            verify_smoke([call, RESULT, TextDelta("703")])

    def test_rejects_an_expression_exceeding_the_calculator_limit(self):
        expression = "37 * 19".rjust(_MAX_EXPRESSION_LENGTH + 1)
        call = ToolCall(CALL.id, "calculate", {"expression": expression})
        with self.assertRaisesRegex(SmokeFailure, "did not use calculate"):
            verify_smoke([call, RESULT, TextDelta("703")])

    def test_accepts_valid_retry_after_a_malformed_expression(self):
        malformed_call = ToolCall("failed-attempt", "calculate", {"expression": "\ud800"})
        failed_result = ToolResult(malformed_call.id, ("Invalid expression",), True)
        verify_smoke([malformed_call, failed_result, CALL, RESULT, TextDelta("703")])

    def test_rejects_a_missing_unmatched_failed_or_incorrect_result(self):
        for results in (
            [],
            [ToolResult("unknown", ("703",), False)],
            [ToolResult(CALL.id, ("703",), True)],
            [ToolResult(CALL.id, ("702",), False)],
            [ToolResult(CALL.id, ("Error message containing 703",), False)],
        ):
            with self.subTest(results=results), self.assertRaisesRegex(SmokeFailure, "No successful"):
                verify_smoke([CALL, *results, TextDelta("703")])

    def test_uses_only_visible_text_from_the_final_reply(self):
        for events in (
            [TextDelta("703"), CALL, RESULT],
            [CALL, RESULT, TextDelta("703", reasoning=True)],
            [CALL, RESULT, TextDelta("703"), ToolCall("another", "other_tool", {}), TextDelta("Done.")],
        ):
            with self.subTest(events=events), self.assertRaisesRegex(SmokeFailure, "final reply"):
                verify_smoke(events)

    def test_rejects_the_digits_inside_an_unrelated_number_or_word(self):
        for answer in ("1703", "7030", "1,703", "703.5", "0.703", "-703", "703e-2", "id703"):
            with self.subTest(answer=answer), self.assertRaisesRegex(SmokeFailure, "final reply"):
                verify_smoke([CALL, RESULT, TextDelta(answer)])

    def test_rejects_a_contradictory_reply(self):
        with self.assertRaisesRegex(SmokeFailure, "final reply"):
            verify_smoke([CALL, RESULT, TextDelta("The tool returned 703, but the answer is 704.")])
