import unittest

from strands import tool

from simple_agent import create_agent
from simple_agent.prompts import SYSTEM_PROMPT


@tool
def echo(text: str) -> str:
    """Return the supplied text unchanged.

    Args:
        text: Text to return.
    """
    return text


class FactoryCustomizationTests(unittest.TestCase):
    def test_agents_have_independent_prompts_tools_and_history(self):
        default = create_agent()
        tool_free = create_agent(tools=[])
        custom_tools = [echo]
        custom = create_agent(system_prompt="Answer as an editor.", tools=custom_tools)
        custom_tools.clear()

        self.assertEqual(default.tool_names, ["current_time", "read_file", "search_text"])
        self.assertEqual(tool_free.tool_names, [])
        self.assertEqual(custom.tool_names, ["echo"])
        self.assertEqual(default.system_prompt, SYSTEM_PROMPT)
        self.assertEqual(tool_free.system_prompt, SYSTEM_PROMPT)
        self.assertEqual(custom.system_prompt, "Answer as an editor.")
        for name in default.tool_names:
            self.assertNotIn(name, tool_free.system_prompt)

        custom.messages.append({"role": "user", "content": [{"text": "Example"}]})
        self.assertEqual(default.messages, [])
        self.assertEqual(tool_free.messages, [])

    def test_default_tool_schemas_include_tool_specific_guidance(self):
        specs = {spec["name"]: spec for spec in create_agent().tool_registry.get_all_tool_specs()}
        self.assertIn("questions about the current time", specs["current_time"]["description"])
        self.assertIn("set both start_line and end_line", specs["read_file"]["description"])
        self.assertIn("Cite the path and line number", specs["search_text"]["description"])
        for spec in specs.values():
            for parameter in spec["inputSchema"]["json"]["properties"].values():
                self.assertTrue(parameter["description"])
