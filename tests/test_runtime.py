import os
import unittest
from unittest.mock import patch

from scripts.run_model import main, model_command


class RuntimeTests(unittest.TestCase):
    def test_hardware_defaults(self):
        cmd = model_command({})
        for flag, value in {"--port": "8088", "--flash-attn": "on",
                            "--cache-type-k": "q8_0", "--cache-type-v": "q8_0",
                            "-t": "4", "-np": "1", "-c": "8192", "-ngl": "99"}.items():
            self.assertEqual(cmd[cmd.index(flag) + 1], value)
        self.assertIn("--jinja", cmd)
        self.assertNotIn("--device", cmd)
        self.assertTrue(cmd[2].endswith("gemma-4-E4B-it-Q4_0.gguf"))

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

    def test_cpu_profile_runs_without_device_discovery(self):
        env = {"AGENT_GPU_LAYERS": "99", "AGENT_MODEL": "/tmp/custom.gguf", "LLAMA_ARG_DEVICE": "Vulkan0"}
        with (
            patch("sys.argv", ["run_model.py", "--profile", "uhd620-cpu"]),
            patch.dict(os.environ, env, clear=True),
            patch("scripts.run_model.Path.is_file", return_value=True),
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
