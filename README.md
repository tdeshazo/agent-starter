# Gemma 4 E4B + Strands

A Python starter with an interactive CLI, tools for time, workspace search and file reads,
and a local OpenAI-compatible llama.cpp server. Strands owns the agent/tool loop.
No cloud API key is needed. Text only; no audio/vision projector is loaded.

## Run

Requires Python 3.12+ and uv. The default profile also requires Vulkan drivers
and access to `/dev/dri`.
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
uv run python main.py 'Read pyproject.toml and tell me which Python version it requires.'
uv run python main.py 'Find the max_tokens setting in the agent code. Read the surrounding lines and cite the location.'
uv run python main.py
```

The full-screen TUI supports mouse-wheel and trackpad scrolling (configurable
via `mouse_scroll_speed` in `settings.json`), Page Up/Page Down, Ctrl-Home/Ctrl-End,
and Ctrl-T to open the dedicated transcript view (`↑`/`↓` or `j`/`k`, Home/End,
and `q` or Esc to return), plus Alt+Enter for a newline and Esc to stop a
response. Scrolling up pauses auto-follow so live responses do not jump the
viewport. Type `/` to see commands, including `/clear`, `/exit`, `/pet`,
`/settings`, `/tools`, and `/status`. Piped input uses a line-oriented
interface. Stop the server with Ctrl-C in its terminal. Avoid running dictation
inference simultaneously if GPU memory is limited.

Use `/clear` to start a new conversation and clear the full-screen transcript.

In the full-screen TUI, open `/settings` to edit the agent name and system
prompt. Use Tab to switch fields, Enter for a newline in the prompt, Ctrl-S to
save, or Esc to cancel. An empty system prompt disables it. Saved settings apply
to the next response and persist across launches, including one-shot and piped
use. Saving keeps the current conversation.

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
choices, not new performance measurements. The default profile requires a Vulkan
device and does not silently fall back to CPU.

Export overrides in the shell (no automatic `.env` loading). `DICTATION_ROOT`,
`AGENT_LLAMA_BIN`, and `AGENT_MODEL` override asset locations. `AGENT_PORT`
updates both the server launcher and default client URL. An empty value uses
the default port. Set `AGENT_BASE_URL` to point the client at another host or endpoint.
`python scripts/run_model.py --dry-run` prints the launch command without loading
weights. Assets are never downloaded or modified on startup.

### Intel UHD Graphics 620

The i5-8350U and i5-8365U share these opt-in profiles. Use the CPU profile as a
baseline and compare the Vulkan profile on long prompts.

```sh
uv run python scripts/run_model.py --profile uhd620-cpu
uv run python scripts/run_model.py --profile uhd620-vulkan
```

Both profiles start with Gemma 4 E2B `Q4_0`, a 4096-token context, four CPU
threads, one slot, `f16` KV cache, and automatic Flash Attention. They serve the
model under the API alias `gemma-4-e4b` expected by the agent. Set `AGENT_MODEL`
to an E4B GGUF to compare it on a host with more RAM.

- `uhd620-cpu` uses `--device none` and zero GPU layers, regardless of
  `AGENT_GPU_LAYERS`. A CPU-only llama.cpp build with Gemma 4 support works with
  this profile.
- `uhd620-vulkan` requires a Vulkan device and starts with eight GPU layers.
  Set `AGENT_GPU_LAYERS` to `0` or `99` to compare with zero or full layer
  offload. On a multi-GPU host, use `llama-server --list-devices` to identify
  the Intel device and set `LLAMA_ARG_DEVICE` to its name. Host-memory preference
  is enabled only if `GGML_VK_PREFER_HOST_MEMORY` is present in the environment.

Use `AGENT_LLAMA_BIN` and `AGENT_MODEL` if the assets are installed elsewhere.
Add `--dry-run` to inspect a profile before launching it.

## Extend

Agent setup lives in the `simple_agent` package:

- `agent.py`: `create_agent()` wires the model, prompt, and tools together.
- `prompts.py`: defines the built-in `SYSTEM_PROMPT`.
- `simple_agent/tools/`: add a module with an `@tool`-decorated function and
  register it in `DEFAULT_TOOLS` in the package's `__init__.py`. The built-in
  clock tool lives in `clock.py` and the workspace tools live in `workspace.py`.
  Within the package, `workspace_files.py` owns filesystem access and
  `workspace_text.py` owns text selection and search formatting.
- `conversation.py` manages turns, recovery, and reset for all three CLI modes.
  `strands_backend.py` translates model events, metadata, and failures for that interface.
- `preferences.py` owns preference validation. `settings.py` saves the existing
  JSON format with an adjacent lock file so concurrent updates can merge.

Import the factory with `from simple_agent import create_agent`. Each call creates
fresh conversation state. `simple_agent/cli.py` selects the interface, and
`simple_agent/tui/` handles interactive input and transcript rendering.
Keep tool argument types and docstrings explicit.

- `search_text(query)` searches the current working directory recursively for a
  case-sensitive, single-line literal. Each matching line includes its relative
  path, 1-based line number and an excerpt. Results fit within 4 KiB and contain
  at most 20 matches. Paths containing colons, quotes, backslashes or
  nonprintable characters appear as JSON strings. Search skips symlinks,
  binary files, files over 1 MiB,
  and directories such as `.git`, `.venv`, `__pycache__` and `node_modules`.
  A search can visit up to 10,000 entries, descend 32 levels, and read 32 MiB
  across files. A partial result includes a `Search incomplete` notice.
- `read_file(path)` reads an entire UTF-8 file up to 4 KiB. For a larger file
  (up to 1 MiB), pass both `start_line` and `end_line` to read an inclusive
  range, such as `read_file("simple_agent/agent.py", start_line=25, end_line=35)`.
  The selected text must fit within 4 KiB.

Both tools restrict access to the workspace and exclude `.git`, `.env` and
`.env.*` files except `.env.example`, `.env.sample` and `.env.template`.

The 2048-token output limit applies per inference. Add
application-level limits before exposing more powerful tools. Long conversations
can exhaust the configured context. Use `/clear` when needed.

Uses the official [Strands OpenAI provider](https://strandsagents.com/docs/user-guide/sdk/model-providers/openai/index.md).
Native tool-call quality depends on the model and llama.cpp template; verify new
tools against your own tasks before relying on them.

## Checks

```sh
uv run python -m unittest discover -s tests
uv run simple-agent --help
uv run python main.py --help
uvx ruff check .
```
