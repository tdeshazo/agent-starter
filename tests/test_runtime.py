import unittest
from scripts.run_model import model_command


class RuntimeTests(unittest.TestCase):
    def test_hardware_defaults(self):
        cmd = model_command({})
        for flag, value in {"--port": "8088", "--flash-attn": "on",
                            "--cache-type-k": "q8_0", "--cache-type-v": "q8_0",
                            "-t": "4", "-np": "1", "-c": "8192"}.items():
            self.assertEqual(cmd[cmd.index(flag) + 1], value)
        self.assertIn("--jinja", cmd)
        self.assertTrue(cmd[2].endswith("gemma-4-E4B-it-Q4_0.gguf"))

    def test_overrides(self):
        cmd = model_command({"AGENT_MODEL": "/tmp/model.gguf",
                             "AGENT_PORT": "9000", "AGENT_KV_CACHE_TYPE": "f16"})
        self.assertEqual(cmd[2], "/tmp/model.gguf")
        self.assertEqual(cmd[cmd.index("--port") + 1], "9000")
        self.assertEqual(cmd[cmd.index("--cache-type-v") + 1], "f16")
