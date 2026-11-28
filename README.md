# Gemma 4 E4B + Strands

A Python starter with an interactive CLI, tools for time, workspace search and file reads,
and a local OpenAI-compatible llama.cpp server. Strands owns the agent/tool loop.
No cloud API key is needed. Text only; no audio/vision projector is loaded.

## Install

From the checkout, install the project dependencies with Python 3.12+ and uv.

```sh
uv sync --locked
```

## Your first customization — no model server required

Start a Python session with `uv run python`. Paste these lines to create two
agents and inspect the tools each one can call.

```python
from simple_agent import create_agent
from simple_agent.tools import current_time

planner = create_agent(system_prompt="Help me plan lessons.", tools=())
clock = create_agent(system_prompt="Use the clock for time questions.", tools=(current_time,))
print(planner.tool_names)  # []
print(clock.tool_names)    # ['current_time']
```

The prompt gives each agent its instructions. The `tools` argument selects its
capabilities. Calling `create_agent()` uses the starter prompt and all three
built-in tools. Each agent has its own conversation history.

In the same session, try calling the calculator tool directly. Change the
expression and run it again to see how the tool behaves.

```python
from examples.calculator.agent import calculate

print(calculate("37 * 19"))  # 703
```

Enter `exit()` to return to your shell. The next step runs the same calculation
through the model so you can see when it calls the tool.

## Run

### Self-host the model

From the repository root, create the local runtime and model directories.
Download the llama.cpp release archive for your OS and architecture, then
extract its server executable **and accompanying libraries** into
`.local/runtime/` so that `.local/runtime/llama-server` is executable.
The launcher has been tested with [llama.cpp b12246](https://github.com/ggml-org/llama.cpp/releases/tag/b12246).
If you already installed the server, set `AGENT_LLAMA_BIN` to its executable path.

```sh
mkdir -p .local/runtime .local/models
```

For a CPU-only first run, download the E2B text model (about 2.84 GB) and
launch the CPU profile. The server listens on loopback and can run offline
after setup. The runtime and weights are ignored by Git. [E2B model files](https://huggingface.co/ggml-org/gemma-4-E2B-it-GGUF/tree/main)

```sh
uvx --from huggingface_hub hf download ggml-org/gemma-4-E2B-it-GGUF gemma-4-E2B-it-Q4_0.gguf --local-dir .local/models
uv run python scripts/run_model.py --profile uhd620-cpu
```

For the default Vulkan profile, use a Vulkan-enabled runtime, drivers and
access to `/dev/dri` on Linux. Download the E4B model (about 4.59 GB) and start
the server. [E4B model files](https://huggingface.co/ggml-org/gemma-4-E4B-it-GGUF/tree/main)

```sh
uvx --from huggingface_hub hf download ggml-org/gemma-4-E4B-it-GGUF gemma-4-E4B-it-Q4_0.gguf --local-dir .local/models
uv run python scripts/run_model.py
```

In another terminal, wait for `curl -f http://127.0.0.1:8088/health` to succeed:

```sh
uv run python -m examples.calculator 'Use calculate to multiply 37 by 19.'
```

Look for `Tool #1: calculate` followed by an answer containing `703`.
To try the starter's built-in tools or open its interactive CLI, run one of these commands.

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
`/reasoning`, `/settings`, `/tools`, and `/status`. Piped input uses a line-oriented
interface. Stop the server with Ctrl-C in its terminal. Stop other inference workloads if GPU memory is limited.

Use `/clear` to start a new conversation and clear the full-screen transcript.

In the full-screen TUI, open `/settings` to edit the agent name and system
prompt. Use Tab to switch fields, Enter for a newline in the prompt, Ctrl-S to
save, or Esc to cancel. An empty system prompt disables it. Saved settings apply
to the next response and persist across launches, including one-shot and piped
use. Saving keeps the current conversation.

### Model reasoning

Use `/reasoning on` or `/reasoning off` to change how the model handles the
next prompt. Use `/reasoning` to check the current setting. Each session starts
with reasoning off, and changing it keeps the current conversation.

When the model sends reasoning, click `▸ Reasoning` below that prompt to reveal
it in an indented block. Click `▾ Reasoning` to collapse it again. In the Ctrl-T
transcript view, use Tab or Shift-Tab to move between reasoning controls and
Enter to toggle the focused one. The line-oriented interface prints reasoning
as a labeled, indented block.

Restart any local model server that was launched before this change to enable
per-request reasoning controls.

### Markdown appearance and copying

Markdown headings and table headers use a color scheme modeled on
[Codex's Markdown renderer](https://github.com/openai/codex/blob/045a11fe2c701df09dd31d55e8c3f05e79cc4a77/codex-rs/tui/src/markdown_render.rs):
rose for level-one headings, peach for level two, and yellow for lower headings
and table headers. Heading levels also use bold, underline, and italic styles.
The palette adapts to light backgrounds reported by `COLORFGBG`, with darker
light-theme accents for readability. `NO_COLOR` disables Markdown styling.

In the full-screen transcript, including the Ctrl-T view:

- Drag with the left mouse button to select text. Double-click selects a word,
  triple-click selects a line, and Shift-click extends a selection.
- Press **Ctrl-C** or **Ctrl-Insert** to copy selected text. Copying preserves a
  running response and the input draft. Selected input text can be copied with
  the same shortcuts.
- Press **Esc** to clear the selection, or start typing in the composer.
  With no selection, Ctrl-C keeps its usual interrupt, clear-input, or quit behavior.
- Responses continue in the background while selected transcript text stays
  fixed. Clear the selection to see new output; Ctrl-End resumes following it
  if the viewport is scrolled up. Mouse-wheel scrolling remains available.

Copying uses the native clipboard when available (`pbcopy` on macOS,
`wl-copy` on Wayland, `xclip` or `xsel` on X11, and `clip.exe` on Windows/WSL).
Otherwise it sends an OSC 52 clipboard request to an interactive terminal,
including tmux passthrough. The footer distinguishes a confirmed native copy
from a request sent to the terminal; terminal clipboard permissions may require
configuration. Copying transfers the displayed text without ANSI color codes.
You can also use your terminal's native selection override (usually Shift-drag,
or Option-drag in some macOS terminals) and its usual copy shortcut.

## Hardware settings

The default Vulkan profile uses these settings:

| Setting | Default | Override |
| --- | --- | --- |
| Vulkan host memory preference | 1 | `GGML_VK_PREFER_HOST_MEMORY` |
| GPU layers | 99 | `AGENT_GPU_LAYERS` |
| Flash attention | on | `AGENT_FLASH_ATTENTION` |
| K/V cache type | q8_0 | `AGENT_KV_CACHE_TYPE` |
| CPU threads | 4 | `AGENT_THREADS` |
| Context tokens | 8192 | `AGENT_CONTEXT_SIZE` |
| Server port | 8088 | `AGENT_PORT` |

The launcher uses one inference slot, disables request logs, and disables
context shift. Jinja enables the model's tool-call chat template. Requests enable
prompt caching and set thinking according to the session's `/reasoning` setting.
The default profile requires a Vulkan device.

Export overrides in the shell (no automatic `.env` loading). `AGENT_LLAMA_BIN`, and `AGENT_MODEL` override asset locations. `AGENT_PORT`
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

To adapt the [calculator example](examples/calculator/agent.py), start with
`create_calculator_agent()` at the bottom of the file. This is where you pair
your own prompt with a tuple of tools.

Run its tool tests locally, then use the smoke check with the model server running
to verify the tool call, its result, and the final answer.

```sh
uv run python -m unittest discover -s tests -p test_calculator_example.py -v
uv run python -m examples.calculator.smoke
```

For a prompt beginning with a minus sign, use the argument separator, as in
`uv run python -m examples.calculator -- '-2+3'`.

Agent setup lives in the `simple_agent` package:

- `agent.py`: `create_agent()` wires the model, prompt, and tools together.
- `prompts.py`: defines the built-in `SYSTEM_PROMPT`.
- `simple_agent/tools/` holds the built-in tools. To change which tools every
  default agent gets, edit `DEFAULT_TOOLS` in the package's `__init__.py`. The built-in
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
Within the TUI, `history.py` owns transcript selection and `clipboard.py` owns
native and terminal clipboard writes; `markdown.py` owns Markdown styling and layout.
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
