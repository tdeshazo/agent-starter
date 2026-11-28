import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from httpx import AsyncClient, MockTransport, Response
from openai import AsyncOpenAI

from scripts.run_model import main, model_command
from simple_agent.agent import create_agent, create_conversation, resolve_base_url
from simple_agent.conversation import TextDelta
from simple_agent.preferences import UserPreferences
from simple_agent.strands_backend import LocalOpenAIModel


class RuntimeTests(unittest.TestCase):
    def test_hardware_defaults(self):
        cmd = model_command({})
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(Path(cmd[0]), root / ".local/runtime/llama-server")
        self.assertEqual(Path(cmd[2]), root / ".local/models/gemma-4-E4B-it-Q4_0.gguf")
        for flag, value in {"--port": "8088", "--flash-attn": "on",
                            "--cache-type-k": "q8_0", "--cache-type-v": "q8_0",
                            "-t": "4", "-np": "1", "-c": "8192", "-ngl": "99"}.items():
            self.assertEqual(cmd[cmd.index(flag) + 1], value)
        self.assertIn("--jinja", cmd)
        self.assertNotIn("--device", cmd)
        self.assertTrue(cmd[2].endswith("gemma-4-E4B-it-Q4_0.gguf"))

    def test_empty_port_uses_same_default_for_server_and_client(self):
        env = {"AGENT_PORT": ""}
        cmd = model_command(env)
        self.assertEqual(cmd[cmd.index("--port") + 1], "8088")
        self.assertEqual(resolve_base_url(env), "http://127.0.0.1:8088/v1")

    def test_overrides(self):
        cmd = model_command({"AGENT_MODEL": "/tmp/model.gguf",
                             "AGENT_PORT": "9000", "AGENT_KV_CACHE_TYPE": "f16"})
        self.assertEqual(cmd[2], "/tmp/model.gguf")
        self.assertEqual(cmd[cmd.index("--port") + 1], "9000")
        self.assertEqual(cmd[cmd.index("--cache-type-v") + 1], "f16")

    def test_uhd620_profile_defaults(self):
        for profile, layers in {"uhd620-cpu": "0", "uhd620-vulkan": "8"}.items():
            with self.subTest(profile=profile):
                cmd = model_command({}, profile)
                self.assertTrue(cmd[2].endswith("gemma-4-E2B-it-Q4_0.gguf"))
                for flag, value in {"--alias": "gemma-4-e4b", "-ngl": layers, "-c": "4096",
                                    "--flash-attn": "auto", "--cache-type-k": "f16",
                                    "--cache-type-v": "f16", "-t": "4", "-np": "1"}.items():
                    self.assertEqual(cmd[cmd.index(flag) + 1], value)

    def test_all_profiles_support_request_reasoning_with_thinking_off_by_default(self):
        for profile in ("default", "uhd620-cpu", "uhd620-vulkan"):
            with self.subTest(profile=profile):
                cmd = model_command({}, profile)
                self.assertEqual(cmd[cmd.index("--reasoning") + 1], "off")
                self.assertEqual(cmd[cmd.index("--reasoning-format") + 1], "deepseek")

    def test_cpu_profile_runs_without_device_discovery(self):
        env = {"AGENT_GPU_LAYERS": "99", "AGENT_MODEL": "/tmp/custom.gguf", "LLAMA_ARG_DEVICE": "Vulkan0"}
        with (
            patch("sys.argv", ["run_model.py", "--profile", "uhd620-cpu"]),
            patch.dict(os.environ, env, clear=True),
            patch("scripts.run_model.Path.is_file", return_value=True),
            patch("scripts.run_model.os.access", return_value=True),
            patch("scripts.run_model.subprocess.run") as list_devices,
            patch("scripts.run_model.os.execve") as launch,
        ):
            main()

        list_devices.assert_not_called()
        launch.assert_called_once()
        _, cmd, launch_env = launch.call_args.args
        self.assertEqual(cmd[2], "/tmp/custom.gguf")
        self.assertEqual(cmd[cmd.index("-ngl") + 1], "0")
        self.assertEqual(cmd[cmd.index("--device") + 1], "none")
        self.assertNotIn("LLAMA_ARG_DEVICE", launch_env)

    def test_vulkan_profiles_run_device_discovery_and_apply_host_memory_defaults(self):
        for args, env, host_memory, layers in (
            ([], {}, "1", "99"),
            (["--profile", "uhd620-vulkan"], {}, None, "8"),
            (["--profile", "uhd620-vulkan"], {"AGENT_GPU_LAYERS": "99",
                                              "GGML_VK_PREFER_HOST_MEMORY": "1"}, "1", "99"),
        ):
            with (
                self.subTest(args=args, env=env),
                patch("sys.argv", ["run_model.py", *args]),
                patch.dict(os.environ, env, clear=True),
                patch("scripts.run_model.Path.is_file", return_value=True),
                patch("scripts.run_model.os.access", return_value=True),
                patch("scripts.run_model.subprocess.run") as list_devices,
                patch("scripts.run_model.os.execve") as launch,
            ):
                list_devices.return_value.returncode = 0
                list_devices.return_value.stdout = "Available devices:\n  Vulkan0: test GPU\n"
                main()

                launch.assert_called_once()
                binary, cmd, launch_env = launch.call_args.args
                list_devices.assert_called_once_with(
                    [binary, "--list-devices"], env=launch_env, capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(launch_env.get("GGML_VK_PREFER_HOST_MEMORY"), host_memory)
                self.assertEqual(cmd[cmd.index("-ngl") + 1], layers)


class ReasoningHistoryTests(unittest.TestCase):
    def test_reasoning_is_omitted_from_requests_without_losing_text_or_tools(self):
        thought = {"reasoningContent": {"reasoningText": {"text": "Thought"}}}
        messages = [
            {
                "role": "assistant",
                "content": [
                    thought,
                    {"text": "Answer"},
                    {"toolUse": {"toolUseId": "1", "name": "test", "input": {}}},
                ],
            },
            {
                "role": "user",
                "content": [{"toolResult": {"toolUseId": "1", "content": [{"text": "Result"}]}}],
            },
        ]

        with self.assertNoLogs("strands.models.openai"):
            assistant, tool = LocalOpenAIModel.format_request_messages(messages)

        self.assertEqual(assistant["content"], [{"type": "text", "text": "Answer"}])
        self.assertEqual(assistant["tool_calls"][0]["function"]["name"], "test")
        self.assertEqual(tool["tool_call_id"], "1")
        self.assertEqual(tool["content"], "Result")
        self.assertEqual(messages[0]["content"][0], thought)


class ReasoningRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_reasoning_controls_request_and_persists_across_reset(self):
        requests = []
        events = []

        def respond(request):
            body = json.loads(request.content)
            requests.append(body)
            deltas = []
            if body["chat_template_kwargs"]["enable_thinking"]:
                deltas.append({"reasoning_content": "Thought"})
            deltas.append({"content": "Answer"})
            chunks = [
                {
                    "id": "test", "created": 0, "model": body["model"], "object": "chat.completion.chunk",
                    "choices": [{"delta": delta, "index": 0, "finish_reason": None if delta else "stop"}],
                }
                for delta in [*deltas, {}]
            ]
            return Response(
                200,
                headers={"content-type": "text/event-stream"},
                text="".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n",
            )

        def build_model(client_args, **config):
            config["params"]["extra_body"]["chat_template_kwargs"]["other_option"] = "kept"
            return LocalOpenAIModel(client=client, **config)

        settings = {}
        preferences = UserPreferences(settings.copy, settings.update)
        http_client = AsyncClient(transport=MockTransport(respond))
        async with AsyncOpenAI(api_key="test", http_client=http_client) as client:
            with (
                # Avoid an unrelated OpenAI platform probe in the event loop's thread pool.
                patch.object(client, "_platform", "Unknown"),
                patch("simple_agent.agent.LocalOpenAIModel", side_effect=build_model),
            ):
                conversation = create_conversation(create_agent, preferences)
                conversation.observe(events.append)
                await conversation.invoke_async("first")
                conversation.set_reasoning(True)
                await conversation.invoke_async("second")
                conversation.reset()
                await conversation.invoke_async("fresh")
                conversation.set_reasoning(False)
                await conversation.invoke_async("last")

        self.assertEqual(
            [body["chat_template_kwargs"]["enable_thinking"] for body in requests],
            [False, True, True, False],
        )
        for body in requests:
            self.assertEqual(body["chat_template_kwargs"]["other_option"], "kept")
            self.assertIs(body["cache_prompt"], True)
            self.assertEqual(body["temperature"], 0.2)
            self.assertEqual(body["max_tokens"], 2048)
        self.assertEqual(
            [[message["content"][0]["text"] for message in body["messages"] if message["role"] == "user"]
             for body in requests],
            [["first"], ["first", "second"], ["fresh"], ["fresh", "last"]],
        )
        self.assertEqual(
            [event for event in events if isinstance(event, TextDelta)],
            [TextDelta("Answer"), TextDelta("Thought", reasoning=True), TextDelta("Answer"),
             TextDelta("Thought", reasoning=True), TextDelta("Answer"), TextDelta("Answer")],
        )
