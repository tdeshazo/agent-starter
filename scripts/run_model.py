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
    root = Path(__file__).resolve().parents[1]
    default_binary = root / ".local/runtime/llama-server"
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
        "--no-context-shift", "--no-webui", "--jinja",
        # Requests can override the thinking default via chat_template_kwargs.
        "--reasoning", "off", "--reasoning-format", "deepseek", "--log-disable",
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
    if not Path(command[0]).is_file() or not os.access(command[0], os.X_OK):
        parser.error(f"Missing executable {command[0]}. See README or set AGENT_LLAMA_BIN.")
    if not Path(command[2]).is_file():
        parser.error(f"Missing model {command[2]}. Download the GGUF or set AGENT_MODEL. See README.")
    if args.profile != "uhd620-cpu":
        result = subprocess.run(
            [command[0], "--list-devices"], env=env, capture_output=True, text=True, timeout=30,
        )
        if result.returncode or not re.search(r"^\s*Vulkan\d+:", result.stdout, re.MULTILINE):
            parser.error("No Vulkan device detected. Check Vulkan drivers and /dev/dri access.")
    os.execve(command[0], command, env)


if __name__ == "__main__":
    main()
