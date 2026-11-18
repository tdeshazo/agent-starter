# Gemma 4 E4B + Strands

A Python starter with an interactive CLI, a `current_time` example tool, and a local
OpenAI-compatible llama.cpp server. Strands owns the agent/tool loop. No cloud API
key is needed. Text only; no audio/vision projector is loaded.

## Run

Requires Python 3.12+, uv, Vulkan drivers and access to `/dev/dri`.
By default, reuses these existing assets from `~/Workspace/dictation`:

- `.local/runtime/llama-b12246/llama-server`
- `.local/models/gemma-4-E4B-it-Q4_0.gguf`

```sh
uv sync --locked
uv run python scripts/run_model.py
```

In another terminal, wait for `curl -f http://127.0.0.1:8088/health` to succeed:

```sh
uv run python main.py 'Use current_time to tell me the time in America/New_York.'
uv run python main.py
```

Use `/reset` to clear the conversation and `/quit` to exit. Stop the server with
Ctrl-C in its terminal. Avoid running dictation inference simultaneously if GPU
memory is limited; this process loads a separate copy of the weights.

## Hardware settings

Port 8088 keeps this server separate from dictation's 8087. Defaults are taken
from dictation's `app/engine.py` and its documented configuration F:

| Setting | Default | Override |
| --- | --- | --- |
| Vulkan host memory preference | 1 | `GGML_VK_PREFER_HOST_MEMORY` |
| GPU layers | 99 | `AGENT_GPU_LAYERS` |
| Flash attention | on | `AGENT_FLASH_ATTENTION` |
| K/V cache type | q8_0 | `AGENT_KV_CACHE_TYPE` |
| CPU threads | 4 | `AGENT_THREADS` |
| Context tokens | 8192 | `AGENT_CONTEXT_SIZE` |
| Server port | 8088 | `AGENT_PORT` |

One inference slot, disabled reasoning, disabled request logs and no context shift
match dictation. Jinja enables the model's tool-call chat template. Requests also
explicitly disable thinking and enable prompt caching. These are inherited tuning
choices, not new performance measurements. The launcher requires a Vulkan device
and does not silently fall back to CPU.

Export overrides in the shell (no automatic `.env` loading). `DICTATION_ROOT`,
`AGENT_LLAMA_BIN`, and `AGENT_MODEL` override asset locations. Changing the port
also requires `AGENT_BASE_URL=http://127.0.0.1:PORT/v1` for the client.
`python scripts/run_model.py --dry-run` prints the launch command without loading
weights. Assets are never downloaded or modified on startup. On another machine,
provision a Vulkan llama.cpp build with Gemma 4 support and E4B GGUF weights first.

## Extend

Agent setup lives in the `simple_agent` package:

- `agent.py`: `create_agent()` wires the model, prompt, and tools together.
- `prompts.py`: edit `SYSTEM_PROMPT` to define the agent's behavior.
- `tools.py`: add functions decorated with `@tool` and register them in `DEFAULT_TOOLS`.

Import the factory with `from simple_agent import create_agent`. Each call creates
fresh conversation state. `main.py` handles only the CLI and conversation reset.
Keep tool argument types and docstrings explicit. The default tool
only reads the clock. The 2048-token output limit is per inference, not a total
agent-loop limit; add application-level limits before exposing more powerful tools.
Long conversations can exhaust the 8K context; use `/reset` when needed.

Uses the official [Strands OpenAI provider](https://strandsagents.com/docs/user-guide/sdk/model-providers/openai/index.md).
Native tool-call quality depends on the model and llama.cpp template; verify new
tools against your own tasks before relying on them.

## Checks

```sh
uv run python -m unittest discover -s tests
uv run python main.py --help
```
