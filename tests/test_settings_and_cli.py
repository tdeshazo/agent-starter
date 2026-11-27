from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import tempfile
from threading import Event
from types import SimpleNamespace
import unittest
from unittest import mock

from simple_agent import settings
from simple_agent.agent import create_agent, resolve_base_url
from simple_agent.cli import main, run_cli
from simple_agent.settings import (
    DEFAULT_AGENT_NAME,
    apply_agent_settings,
    load_settings,
    normalize_agent_name,
    save_settings,
)
from simple_agent.tui import load_pet


class SettingsTests(unittest.TestCase):
    def test_normalize_agent_name_rejects_blank_and_control_characters(self):
        self.assertIsNone(normalize_agent_name(None))
        self.assertIsNone(normalize_agent_name(123))
        self.assertIsNone(normalize_agent_name("   "))
        self.assertIsNone(normalize_agent_name("Two\nLines"))
        self.assertIsNone(normalize_agent_name("Tab\tName"))
        self.assertIsNone(normalize_agent_name("Esc\x1b[31m"))
        self.assertIsNone(normalize_agent_name("LineSep\u2028Name"))
        self.assertEqual(normalize_agent_name("  Local Helper  "), "Local Helper")

    def test_apply_agent_settings_handles_empty_system_prompt_and_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "settings.json"
            agent = SimpleNamespace(name=DEFAULT_AGENT_NAME, system_prompt="Built-in")
            apply_agent_settings(agent, config)
            self.assertEqual(agent.name, DEFAULT_AGENT_NAME)
            self.assertEqual(agent.system_prompt, "Built-in")

            save_settings({"agent_name": "Scout", "system_prompt": ""}, config)
            apply_agent_settings(agent, config)
            self.assertEqual(agent.name, "Scout")
            self.assertIsNone(agent.system_prompt)

            config.write_text('["not-a-dict"]\n', encoding="utf-8")
            self.assertEqual(load_settings(config), {})


    def test_concurrent_saves_merge_distinct_preferences(self):
        started = Event()
        second_lock = Event()
        first_committed = Event()
        replace_settings = settings._replace_settings
        flock = settings.fcntl.flock

        def wait_before_replace(path, data):
            if "agent_name" in data and "pet" not in data:
                started.set()
                if not second_lock.wait(timeout=5):
                    raise AssertionError("Second writer did not attempt to acquire the lock")
                replace_settings(path, data)
                first_committed.set()
            else:
                self.assertTrue(first_committed.is_set())
                replace_settings(path, data)

        def observe_lock(fd, flags):
            if started.is_set():
                second_lock.set()
            flock(fd, flags)

        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "settings.json"
            with (
                mock.patch.object(settings, "_replace_settings", side_effect=wait_before_replace),
                mock.patch.object(settings.fcntl, "flock", side_effect=observe_lock),
                ThreadPoolExecutor(max_workers=2) as workers,
            ):
                first = workers.submit(save_settings, {"agent_name": "Guide"}, config)
                self.assertTrue(started.wait(timeout=5))
                second = workers.submit(save_settings, {"pet": "frog"}, config)
                first.result(timeout=5)
                second.result(timeout=5)
            self.assertEqual(load_settings(config), {"agent_name": "Guide", "pet": "frog"})


class BaseUrlTests(unittest.TestCase):
    def test_resolve_base_url_syncs_with_agent_port_and_prefers_explicit_url(self):
        self.assertEqual(resolve_base_url({}), "http://127.0.0.1:8088/v1")
        self.assertEqual(resolve_base_url({"AGENT_PORT": "9090"}), "http://127.0.0.1:9090/v1")
        self.assertEqual(
            resolve_base_url(
                {"AGENT_PORT": "9090", "AGENT_BASE_URL": "http://10.0.0.2:8000/v1"}
            ),
            "http://10.0.0.2:8000/v1",
        )
        with mock.patch.dict(os.environ, {"AGENT_PORT": "8123"}, clear=True):
            agent = create_agent()
            self.assertEqual(agent.model.client_args["base_url"], "http://127.0.0.1:8123/v1")


class CliTests(unittest.TestCase):
    def test_one_shot_cli_applies_settings_and_persists_pet(self):
        calls = []

        class StubAgent:
            def __init__(self):
                self.name = DEFAULT_AGENT_NAME
                self.system_prompt = "Default"
                self.messages = []

            def __call__(self, prompt):
                calls.append((prompt, self.name, self.system_prompt))

        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "settings.json"
            save_settings({"agent_name": "Helper", "system_prompt": "Be brief."}, config)
            out = io.StringIO()
            with redirect_stdout(out):
                code = run_cli(
                    ["--pet", "moth", "Say hello"],
                    agent_factory=StubAgent,
                    config_path=config,
                )
            self.assertEqual(code, 0)
            self.assertEqual(load_pet(config), "moth")
            self.assertEqual(calls, [("Say hello", "Helper", "Be brief.")])

    def test_one_shot_cli_formats_errors_and_interrupts_without_traceback(self):
        class APIConnectionError(Exception):
            pass

        def failing_factory():
            def invoke(_prompt):
                raise APIConnectionError("connection refused")

            return invoke

        err = io.StringIO()
        with redirect_stderr(err):
            code = run_cli(["Hello"], agent_factory=failing_factory)
        self.assertEqual(code, 1)
        self.assertIn("APIConnectionError: Could not connect to model server", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())

        prior = {"role": "assistant", "content": [{"text": "Earlier"}]}

        class InterruptAgent:
            def __init__(self):
                self.messages = [prior]

            def __call__(self, prompt):
                self.messages[0]["content"][0]["text"] = "Changed during turn"
                self.messages.append({"role": "user", "content": [{"text": prompt}]})
                raise KeyboardInterrupt

        agent = InterruptAgent()
        err_interrupt = io.StringIO()
        with redirect_stderr(err_interrupt):
            code = run_cli(["Stop me"], agent_factory=lambda: agent)
        self.assertEqual(code, 130)
        self.assertEqual(agent.messages, [{"role": "assistant", "content": [{"text": "Earlier"}]}])
        self.assertIn("Response stopped", err_interrupt.getvalue())

        with mock.patch("simple_agent.cli.run_cli", return_value=1):
            with self.assertRaises(SystemExit) as ctx:
                main(["boom"])
            self.assertEqual(ctx.exception.code, 1)
