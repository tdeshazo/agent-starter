"""Launch the existing dictation Vulkan runtime with an independent model slot."""
import argparse
import os
from pathlib import Path
import re
import shlex
import subprocess


def model_command(env):
    root = Path(env.get("DICTATION_ROOT", "~/Workspace/dictation")).expanduser()
    binary = Path(env.get("AGENT_LLAMA_BIN", str(root / ".local/runtime/llama-b12246/llama-server"))).expanduser()
    model = Path(env.get("AGENT_MODEL", str(root / ".local/models/gemma-4-E4B-it-Q4_0.gguf"))).expanduser()
    return [str(binary), "-m", str(model), "--alias", "gemma-4-e4b",
            "--host", "127.0.0.1", "--port", env.get("AGENT_PORT", "8088"),
            "-ngl", env.get("AGENT_GPU_LAYERS", "99"),
            "-c", env.get("AGENT_CONTEXT_SIZE", "8192"),
            "--flash-attn", env.get("AGENT_FLASH_ATTENTION", "on"),
            "--cache-type-k", env.get("AGENT_KV_CACHE_TYPE", "q8_0"),
            "--cache-type-v", env.get("AGENT_KV_CACHE_TYPE", "q8_0"),
            "-t", env.get("AGENT_THREADS", "4"), "-np", "1",
            "--no-context-shift", "--no-webui", "--jinja", "--reasoning", "off",
            "--chat-template-kwargs", '{"enable_thinking":false}', "--log-disable"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    env = dict(os.environ)
    env.setdefault("GGML_VK_PREFER_HOST_MEMORY", "1")
    command = model_command(env)
    if args.dry_run:
        print("GGML_VK_PREFER_HOST_MEMORY=" + shlex.quote(env["GGML_VK_PREFER_HOST_MEMORY"]))
        print(shlex.join(command))
        return
    for path in (command[0], command[2]):
        if not Path(path).is_file():
            parser.error(f"Missing {path}; set AGENT_LLAMA_BIN / AGENT_MODEL or provision dictation assets.")
    result = subprocess.run([command[0], "--list-devices"], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode or not re.search(r"^\s*Vulkan\d+:", result.stdout, re.MULTILINE):
        parser.error("No Vulkan device detected. Check Vulkan drivers and /dev/dri access.")
    os.execve(command[0], command, env)


if __name__ == "__main__":
    main()
