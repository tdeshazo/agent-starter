"""Launch llama.cpp with an independent model slot."""

import argparse
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path


if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simple_agent.config import MODEL_HOST, MODEL_ID, model_port  # noqa: E402


def model_command(env, profile="default"):
    intel_profile = profile != "default"
    cpu_only = profile == "uhd620-cpu"
    root = Path(env.get("DICTATION_ROOT", "~/Workspace/dictation")).expanduser()
    default_binary = root / ".local/runtime/llama-b12246/llama-server"
    model_size = "E2B" if intel_profile else "E4B"
    default_model = root / f".local/models/gemma-4-{model_size}-it-Q4_0.gguf"
    binary = Path(env.get("AGENT_LLAMA_BIN", default_binary)).expanduser()
    model = Path(env.get("AGENT_MODEL", default_model)).expanduser()
    cache_type = env.get("AGENT_KV_CACHE_TYPE", "f16" if intel_profile else "q8_0")
    gpu_layers = "0" if cpu_only else env.get("AGENT_GPU_LAYERS", "8" if intel_profile else "99")
    command = [
        str(binary), "-m", str(model), "--alias", MODEL_ID,
        "--host", MODEL_HOST, "--port", model_port(env),
        "-ngl", gpu_layers,
        "-c", env.get("AGENT_CONTEXT_SIZE", "4096" if intel_profile else "8192"),
        "--flash-attn", env.get("AGENT_FLASH_ATTENTION", "auto" if intel_profile else "on"),
        "--cache-type-k", cache_type, "--cache-type-v", cache_type,
        "-t", env.get("AGENT_THREADS", "4"), "-np", "1",
        "--no-context-shift", "--no-webui", "--jinja", "--reasoning", "off",
        "--chat-template-kwargs", '{"enable_thinking":false}', "--log-disable",
    ]
    if cpu_only:
        command.extend(["--device", "none"])
    return command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile", choices=("default", "uhd620-cpu", "uhd620-vulkan"), default="default",
        help="inference settings for the current host (default) or Intel UHD Graphics 620",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    env = dict(os.environ)
    if args.profile == "default":
        env.setdefault("GGML_VK_PREFER_HOST_MEMORY", "1")
    elif args.profile == "uhd620-cpu":
        # llama.cpp validates the environment's device before applying CLI flags.
        env.pop("LLAMA_ARG_DEVICE", None)
    command = model_command(env, args.profile)
    if args.dry_run:
        if "GGML_VK_PREFER_HOST_MEMORY" in env:
            print("GGML_VK_PREFER_HOST_MEMORY=" + shlex.quote(env["GGML_VK_PREFER_HOST_MEMORY"]))
        print(shlex.join(command))
        return
    for path in (command[0], command[2]):
        if not Path(path).is_file():
            parser.error(
                f"Missing {path}; set AGENT_LLAMA_BIN / AGENT_MODEL or provision dictation assets."
            )
    if args.profile != "uhd620-cpu":
        result = subprocess.run(
            [command[0], "--list-devices"], env=env, capture_output=True, text=True, timeout=30,
        )
        if result.returncode or not re.search(r"^\s*Vulkan\d+:", result.stdout, re.MULTILINE):
            parser.error("No Vulkan device detected. Check Vulkan drivers and /dev/dri access.")
    os.execve(command[0], command, env)


if __name__ == "__main__":
    main()
