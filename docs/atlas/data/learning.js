// Progressive hands-on coding exercises (hints & solutions hidden by default)
// and comprehension questions (answers hidden by default).

window.ATLAS_EXERCISES = [
  {
    id: "ex-1",
    level: "Level 1 · Trace & Observe",
    subsystem: "Orchestration & Runtime",
    title: "Trace a Custom Port End-to-End Without Starting a Model",
    goal: "Verify how AGENT_PORT synchronizes the server launcher (scripts/run_model.py) and the client agent factory (simple_agent/agent.py), and observe what happens when AGENT_BASE_URL is also set.",
    targets: ["scripts/run_model.py:24", "simple_agent/agent.py:13-19", "tests/test_settings_and_cli.py:50-63"],
    task: "1) Run `AGENT_PORT=9123 uv run python scripts/run_model.py --dry-run` and confirm `--port 9123` appears.\n2) In Python, call `resolve_base_url({'AGENT_PORT': '9123'})` and `resolve_base_url({'AGENT_PORT': '9123', 'AGENT_BASE_URL': 'http://10.0.0.5:8000/v1'})`.\n3) Explain why `resolve_base_url` takes an optional `env: Mapping[str, str] | None = None` parameter instead of always reading `os.environ` directly.",
    verifyCmd: ".venv/bin/python -m unittest tests.test_settings_and_cli.BaseUrlTests -v",
    hints: [
      "Look at `simple_agent/agent.py:15`: `source = os.environ if env is None else env`.",
      "Injecting `env` makes pure unit testing possible without mutating process-global `os.environ`, while `create_agent()` still calls `resolve_base_url()` with no arguments."
    ],
    solution: "AGENT_BASE_URL wins over AGENT_PORT because `if base_url := source.get('AGENT_BASE_URL'): return base_url` runs first. Accepting `env` as an optional mapping is lightweight dependency injection: `BaseUrlTests` tests 3 cases purely with dicts and only patches `os.environ` once to verify `create_agent()` wiring."
  },
  {
    id: "ex-2",
    level: "Level 2 · Debug & Diagnose",
    subsystem: "Memory & Turn Rollback",
    title: "Reproduce & Reason About Mid-Tool-Call Interruption",
    goal: "Understand how `conversation_turn()` and `AgentTui.interrupt()` cooperate when a user hits Esc after a toolUse has been appended to `agent.messages`.",
    targets: ["simple_agent/tui/session.py:10-19", "simple_agent/tui/app.py:844-863", "tests/test_tui.py:626-673"],
    task: "1) Read `test_escape_stops_stream_and_restores_history` in `tests/test_tui.py`.\n2) Trace what would happen if `conversation_turn` caught `Exception` instead of `BaseException`.\n3) Trace what would happen if `conversation_turn` wrote `messages = history` instead of `messages[:] = history`.",
    verifyCmd: ".venv/bin/python -m unittest tests.test_tui.AgentTuiTests.test_escape_stops_stream_and_restores_history -v",
    hints: [
      "Check Python's exception hierarchy for `asyncio.CancelledError` and `KeyboardInterrupt`.",
      "`messages = history` only rebinds the local parameter name inside `conversation_turn`, leaving the caller's `agent.messages` list untouched!"
    ],
    solution: "1) In Python 3.8+, `asyncio.CancelledError` and `KeyboardInterrupt` inherit from `BaseException`, not `Exception`. Catching `Exception` would skip rollback on Esc and Ctrl-C, leaving an orphaned user/toolUse message in `agent.messages`. 2) `messages[:] = history` mutates the list object in place so `agent.messages` (and any internal Strands reference to it) is restored."
  },
  {
    id: "ex-3",
    level: "Level 3 · Extend Safely",
    subsystem: "Tools & Workspace Security",
    title: "Design a Safe `list_directory` Tool Following `tools.py` Invariants",
    goal: "Practice designing a new Strands `@tool` that upholds every security and resource-budget invariant already enforced by `read_file` and `search_text`.",
    targets: ["simple_agent/tools.py:14-72", "simple_agent/tools.py:142-255", "simple_agent/prompts.py:3-10", "tests/test_tools.py"],
    task: "Design (on paper or in a scratch branch) a `list_directory(path: str = '.') -> str` tool:\n1) Which flags should open the target directory?\n2) Which entries must be hidden or skipped?\n3) What output cap (entry count & byte limit) and truncation notice should it enforce?\n4) Which files must be updated to wire it into the agent and document it for the model?",
    verifyCmd: ".venv/bin/python -m unittest tests.test_tools -v",
    hints: [
      "Check `DIRECTORY_READ_FLAGS` (`os.O_DIRECTORY | os.O_NOFOLLOW | os.O_RDONLY`) and `_is_sensitive_path()` in `simple_agent/tools.py`.",
      "Remember to register in `DEFAULT_TOOLS` (`tools.py:255`) and align `SYSTEM_PROMPT` (`prompts.py:3-10`) so Gemma knows when to invoke it."
    ],
    solution: "1) Resolve & verify `resolved.is_relative_to(root)`, reject `_is_sensitive_path(rel_parts)`, and open via dir_fd using `DIRECTORY_LOOKUP_FLAGS` for ancestors and `DIRECTORY_READ_FLAGS` (`O_DIRECTORY | O_NOFOLLOW | O_RDONLY`) for the target directory. 2) Filter out `SEARCH_SKIP_NAMES` and `_is_sensitive_path((entry.name,))`, and do not follow symlinks. 3) Sort deterministically, cap at e.g. 200 entries / 4 KiB (`MAX_FILE_BYTES`), JSON-quote unsafe names, and append a truncation notice if capped. 4) Decorate with `@tool`, add to `DEFAULT_TOOLS`, update `SYSTEM_PROMPT`, and add boundary/symlink/sensitive-file tests in `tests/test_tools.py`."
  },
  {
    id: "ex-4",
    level: "Level 3 · Extend Safely",
    subsystem: "Persistence & TUI",
    title: "Add a New Persistent Preference Without Breaking Existing Keys",
    goal: "Understand how `settings.json` evolves safely across CLI, plain mode, and full-screen TUI.",
    targets: ["simple_agent/settings.py:34-48", "simple_agent/tui/app.py:58-67", "simple_agent/tui/app.py:168-170"],
    task: "Suppose you want to persist a boolean `show_token_usage` preference in `settings.json`.\n1) How does `save_settings({'show_token_usage': False})` avoid wiping `pet`, `agent_name`, `system_prompt`, and `mouse_scroll_speed`?\n2) Why must `_normalize_scroll_speed()` explicitly check `not isinstance(value, bool)`?\n3) Why does `save_settings` create its temp file with `dir=target.parent` instead of `/tmp`?",
    verifyCmd: ".venv/bin/python -m unittest tests.test_settings_and_cli.SettingsTests tests.test_tui.PetTests -v",
    hints: [
      "In Python, `isinstance(True, int)` is `True`!",
      "POSIX `os.replace()` (rename(2)) fails with `EXDEV` across mount points (e.g., `/tmp` on tmpfs vs `/home` on ext4)."
    ],
    solution: "1) `save_settings()` reads the existing JSON dict via `_read_settings(target)` and calls `data.update(updates)` before writing. 2) Because `bool` subclasses `int` in Python, `isinstance(True, (int, float))` would otherwise accept `true` as scroll speed `1.0`. 3) Creating the temp file in `target.parent` guarantees same-filesystem atomic `os.replace()` with no `EXDEV` error and no partial-write window."
  },
  {
    id: "ex-5",
    level: "Level 4 · Architectural Deep-Dive",
    subsystem: "Streaming Markdown & Scroll",
    title: "Diagnose a Hypothetical Table Flicker Bug in `StreamCell`",
    goal: "Master the invariant between `StreamCell.push()` (committed rows) and `StreamCell.tail()` (ephemeral preview).",
    targets: ["simple_agent/tui/rendering.py:407-536", "simple_agent/tui/markdown.py:498-542", "tests/test_tui.py:449-489"],
    task: "1) Explain why `StreamCell.tail()` copies `self.started`, `self.blank_rows`, `self.fence`, `self._list_indents`, and `self._quote_list_indents` into local variables before rendering.\n2) Suppose the model streams `| A | B |\\n` followed by `This is not a table`. At what exact character does `StreamCell` flush `| A | B |` out of `_table_lines`?\n3) How does `test_markdown_streaming_char_by_char_matches_batch_and_previews_live_tail` prove streaming equivalence?",
    verifyCmd: ".venv/bin/python -m unittest tests.test_tui.TranscriptTests.test_markdown_streaming_char_by_char_matches_batch_and_previews_live_tail -v",
    hints: [
      "Look at lines 443-448 of `simple_agent/tui/rendering.py`: `can_be_table_delimiter_prefix(self.line)`.",
      "What happens if `tail()` is called 12.5 times per second by `_animate()` while waiting for the next token?"
    ],
    solution: "1) `tail()` is called on every paint frame (including 80ms `_animate()` ticks). If it mutated `self.started` or `self._list_indents`, subsequent frames or the eventual `push()` commit would drop the bullet or mis-indent lists! 2) On the very first character `'T'` of line 2, `can_be_table_delimiter_prefix('T')` returns `False` (not in `' \\t|:-'`), so `push()` immediately flushes `_table_lines[0]` as a normal Markdown line. 3) The test feeds a complex document 1 character at a time (calling `tail()` after every char) and asserts the final committed rows equal feeding the entire document in a single batch."
  }
];

window.ATLAS_QUIZZES = [
  {
    id: "q-1",
    category: "Orchestration",
    question: "Why does `create_agent()` set `max_retries: 0` on `OpenAIModel` (`simple_agent/agent.py:29`)?",
    answer: "To prevent the OpenAI client from silently retrying slow or failed local llama.cpp requests (which have a 180s timeout and a single inference slot `-np 1`), giving the user immediate feedback and letting `conversation_turn()` roll back cleanly.",
    ref: "simple_agent/agent.py:24-30"
  },
  {
    id: "q-2",
    category: "Memory",
    question: "What happens to `agent.messages` if a user presses `Esc` while `search_text` is running in `AgentTui`?",
    answer: "`AgentTui.interrupt()` sets `stop_requested = True` and cancels `self.task`. `asyncio.CancelledError` unwinds `with conversation_turn(agent.messages):`, which catches `BaseException` and executes `messages[:] = history`, restoring the exact pre-turn message list so no orphaned `toolUse` remains.",
    ref: "simple_agent/tui/session.py:10-19, simple_agent/tui/app.py:844-863"
  },
  {
    id: "q-3",
    category: "Memory",
    question: "Does `/settings` clear the current conversation when you save a new `system_prompt`?",
    answer: "No. `_save_agent_settings()` mutates `self.agent.name` and `self.agent.system_prompt` in place and refreshes the header, keeping `self.agent.messages` intact. Only `/clear` swaps in a fresh `agent_factory()` instance.",
    ref: "simple_agent/tui/app.py:325-329, simple_agent/tui/app.py:823-827"
  },
  {
    id: "q-4",
    category: "Tools & Security",
    question: "Why does `_open_workspace_file()` use `O_PATH` (or `O_SEARCH`) on parent directories instead of `O_RDONLY`?",
    answer: "Traversing to a known file path only requires execute (`+x` / search) permission on ancestor directories, not read (`+r`) permission. Using `O_PATH` allows `read_file()` to open files inside `0o111` search-only ancestor directories while still keeping `O_DIRECTORY | O_NOFOLLOW` protection.",
    ref: "simple_agent/tools.py:27-28, tests/test_tools.py:220-236"
  },
  {
    id: "q-5",
    category: "Tools & Security",
    question: "Why does `read_file()` check `type(start_line) is not int` instead of `not isinstance(start_line, int)`?",
    answer: "In Python, `bool` is a subclass of `int` (`isinstance(True, int) == True`). Checking exact `type(...) is not int` rejects boolean arguments like `start_line=True` from tool calls.",
    ref: "simple_agent/tools.py:98"
  },
  {
    id: "q-6",
    category: "Tools & Security",
    question: "In `search_text()`, why does `result_left` start at `MAX_SEARCH_RESULT_BYTES - len(SEARCH_INCOMPLETE.encode('utf-8'))`?",
    answer: "By reserving the exact byte length of the `SEARCH_INCOMPLETE` notice up front, `search_text()` guarantees that even when a search truncates at the 4 KiB output cap, appending the incomplete notice never pushes the total UTF-8 output past `MAX_SEARCH_RESULT_BYTES` (4096 bytes).",
    ref: "simple_agent/tools.py:194, simple_agent/tools.py:239-244"
  },
  {
    id: "q-7",
    category: "Persistence",
    question: "How do you disable the built-in `SYSTEM_PROMPT` via settings, and how does that differ from omitting `system_prompt` in `settings.json`?",
    answer: "Saving an empty string (`\"system_prompt\": \"\"`) causes `apply_agent_settings()` to run `agent.system_prompt = prompt or None`, which disables the system prompt. Omitting the key (or setting it to a non-string) leaves the built-in `SYSTEM_PROMPT` unchanged.",
    ref: "simple_agent/settings.py:65-66, tests/test_settings_and_cli.py:33-47"
  },
  {
    id: "q-8",
    category: "TUI & Markdown",
    question: "How does `TranscriptControl` know whether to auto-follow new streamed rows or stay pinned where the user scrolled?",
    answer: "Via `self._history.first_line`: when `None`, `create_content()` places the cursor on the last row (`count - 1`) so prompt-toolkit keeps the viewport at the bottom. When the user scrolls up, `_scroll_lines()` sets `first_line` to a non-negative integer row index, pinning the viewport until the user scrolls back to the bottom or submits a new prompt.",
    ref: "simple_agent/tui/app.py:142-148, simple_agent/tui/app.py:586-605"
  },
  {
    id: "q-9",
    category: "TUI & Markdown",
    question: "Why does `parse_inline()` replace backtick code spans with `\\ue000<idx>\\ue001` placeholders before matching bold/italic/link patterns?",
    answer: "To prevent Markdown delimiters inside inline code (like `` `foo_bar_baz` `` or `` `a * b * c` ``) or backslash-escaped characters from being misparsed as emphasis spans in Pass 2. After Pass 2 finishes, `_expand_atoms()` restores the original code text with `CYAN` styling.",
    ref: "simple_agent/tui/markdown.py:196-245"
  },
  {
    id: "q-10",
    category: "Runtime",
    question: "Why does `scripts/run_model.py` pop `LLAMA_ARG_DEVICE` from the environment for `--profile uhd620-cpu`?",
    answer: "`llama-server` validates the `LLAMA_ARG_DEVICE` environment variable before applying CLI flags like `--device none`. Removing it from the child environment ensures a previously exported Vulkan device setting cannot cause the CPU profile to fail.",
    ref: "scripts/run_model.py:49-51, tests/test_runtime.py:36-53"
  }
];
