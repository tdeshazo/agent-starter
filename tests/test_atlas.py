"""Check a few simulator results against the runtime when Node is available."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from simple_agent.tools import read_file


class AtlasReadFileTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is optional for atlas checks")
    def test_shared_simulator_agrees_with_runtime_for_paths_and_range_sizes(self):
        script = Path(__file__).resolve().parents[1] / "docs" / "atlas" / "read-file-policy.js"
        cases = [
            ("/workspace/small.txt", "", "", 2, None),
            ("/workspace/large.txt", "1", "1", 4099, 2),
            ("/workspace/large.txt", "2", "2", 4099, 4097),
            ("/workspace/large.txt", "", "", 4099, None),
        ]
        simulations = [
            dict(path=path, start=start, end=end, kind="regular", size=size, selectedBytes=selected)
            for path, start, end, size, selected in cases
        ]
        node = subprocess.run(
            ["node", "-e", script.read_text(encoding="utf-8") + """
                const input = JSON.parse(require("fs").readFileSync(0, "utf8"));
                const outcomes = input.map(args => {
                    const steps = evaluateAtlasReadFile(args);
                    return steps[steps.length - 1].status;
                });
                console.log(JSON.stringify(outcomes));
            """],
            input=json.dumps(simulations),
            text=True,
            capture_output=True,
            check=True,
        )

        actual = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "small.txt").write_bytes(b"a\n")
            (root / "large.txt").write_bytes(b"a\n" + b"b" * 4097)
            original_dir = Path.cwd()
            try:
                os.chdir(root)
                for path, start, end, _, _ in cases:
                    try:
                        read_file(
                            str(root / Path(path).name),
                            int(start) if start else None,
                            int(end) if end else None,
                        )
                    except ValueError:
                        actual.append("fail")
                    else:
                        actual.append("pass")
            finally:
                os.chdir(original_dir)

        self.assertEqual(json.loads(node.stdout), actual)
