// End-to-end execution walkthroughs with sequence diagrams, call chains,
// state transitions, verbatim source excerpts, breakpoints, and failure scenarios.
// Priority order: 1) Core Agent Orchestration Loop, 2) Memory Management,
// 3) Tool Execution & Security, 4) Persistence, 5) TUI/Markdown/Scroll, 6) Runtime Profiles.

window.ATLAS_WALKTHROUGHS = [
  {
    id: "wt-orchestration",
    priority: "CORE PRIORITY #1",
    title: "1. Core Agent Orchestration Loop & Streaming Turn Lifecycle",
    subtitle: "From user keypress in main.py / AgentTui.submit() through Strands Agent.invoke_async(), local OpenAIModel streaming, tool loop, and Transcript rendering.",
    evidence: "verified",
    dataFlow: [
      "CLI args / TUI Buffer",
      "AgentTui.submit() -> parse_slash_command()",
      "conversation_turn(agent.messages)",
      "Strands Agent.invoke_async(prompt)",
      "OpenAIModel -> HTTP POST :8088/v1/chat/completions",
      "Transcript.__call__(**event) -> StreamCell -> _history.rows / tail()"
    ],
    stateTransitions: [
      "IDLE (task=None)",
      "SUBMITTED (user cell emitted, turn_started set)",
      "STREAMING_OR_TOOLS (task running, _animate() 80ms ticks)",
      "INTERRUPTING (Esc -> stop_requested=True, task.cancel())",
      "FINALIZING (end_turn(): close_stream, separator/usage, invalidate)",
      "IDLE"
    ],
    sequence: {
      actors: ["User / TTY", "AgentTui", "conversation_turn", "Strands Agent", "llama-server", "Transcript"],
      messages: [
        { from: 0, to: 1, label: "Enter prompt in composer", evidence: "verified" },
        { from: 1, to: 5, label: "transcript.user(entered) -> _emit()", evidence: "verified" },
        { from: 1, to: 2, label: "enter with conversation_turn(agent.messages)", evidence: "verified" },
        { from: 2, to: 3, label: "await agent.invoke_async(prompt)", evidence: "verified" },
        { from: 3, to: 4, label: "POST /v1/chat/completions (stream=true, tools)", evidence: "assumption" },
        { from: 4, to: 3, label: "SSE deltas (text / tool_calls / usage)", evidence: "assumption" },
        { from: 3, to: 5, label: "callback_handler(data=..., message=...)", evidence: "verified" },
        { from: 5, to: 1, label: "_emit(committed_rows) + app.invalidate()", evidence: "verified" },
        { from: 1, to: 5, label: "finally: end_turn(elapsed, stopped)", evidence: "verified" }
      ]
    },
    steps: [
      {
        title: "Step 1 — Process Entry & Interface Dispatch",
        evidence: "verified",
        callChain: ["main.py:6 -> main()", "simple_agent/cli.py:71 -> run_cli()", "simple_agent/tui/terminal.py:7 -> interactive_terminal()"],
        explanation: "run_cli() parses optional positional prompt and --pet. If --pet is supplied, it persists immediately via save_pet() before dispatching. A positional prompt runs synchronously via agent(args.prompt) wrapped in conversation_turn(). Without a prompt, interactive_terminal() checks stdin.isatty() and stdout.isatty() and TERM != 'dumb' to choose AgentTui vs run_plain().",
        excerptId: "cli_run"
      },
      {
        title: "Step 2 — Agent & Model Wiring",
        evidence: "verified",
        callChain: ["simple_agent/agent.py:22 -> create_agent()", "simple_agent/agent.py:13 -> resolve_base_url()", "simple_agent/settings.py:60 -> apply_agent_settings()"],
        explanation: "create_agent() builds a Strands OpenAIModel pointed at AGENT_BASE_URL or http://127.0.0.1:${AGENT_PORT:-8088}/v1 with api_key='local', timeout=180.0, max_retries=0, max_tokens=2048, temperature=0.2, cache_prompt=True, and chat_template_kwargs={'enable_thinking': False}. It attaches DEFAULT_TOOLS and SYSTEM_PROMPT, then _set_agent() applies persisted user overrides and binds agent.callback_handler = self.transcript.",
        excerptId: "agent_factory"
      },
      {
        title: "Step 3 — Prompt Submission & Background Task Spawn",
        evidence: "verified",
        callChain: ["simple_agent/tui/app.py:807 -> AgentTui.submit()", "simple_agent/tui/commands.py:47 -> parse_slash_command()", "simple_agent/tui/app.py:841 -> create_background_task(_respond, _animate)"],
        explanation: "submit() ignores input while self.running is True, trims whitespace, saves to InMemoryHistory, resets the composer, jumps scroll to bottom, and checks parse_slash_command(). For normal prompts, it commits the user cell, records monotonic turn_started, clears stop_requested, and spawns two concurrent asyncio tasks: _respond(prompt) and _animate() (12.5 Hz shimmer status ticker).",
        excerptId: "app_submit_respond"
      },
      {
        title: "Step 4 — Strands Callback Event Adaptation & Live Tail",
        evidence: "verified",
        callChain: ["Strands event loop -> Transcript.__call__(**event)", "simple_agent/tui/transcript.py:81 -> _write()", "simple_agent/tui/transcript.py:116 -> _message()", "simple_agent/tui/app.py:228 -> _emit()"],
        explanation: "As Strands streams deltas, Transcript.__call__ routes reasoningText and data into StreamCell.push(), committing immutable completed rows to _history.rows via _emit() while keeping partial lines and running toolUse blocks in tail(). When a toolResult message arrives, the matching toolUseId pops from pending_tools and commits a single 'Called ...' + 3-line truncated result cell.",
        excerptId: "transcript_core"
      },
      {
        title: "Step 5 — Turn Completion, Separator & Token Usage",
        evidence: "verified",
        callChain: ["simple_agent/tui/app.py:861 -> finally:", "simple_agent/tui/transcript.py:148 -> Transcript.end_turn()"],
        explanation: "In _respond()'s finally block, end_turn() flushes StreamCell.finish(), clears pending_tools, prints INTERRUPTED if stopped, emits a '─ Worked for Xs ─' separator if any tool_calls ran, emits aggregated turn usage (in / cached / out) when non-zero, and calls app.invalidate() so the footer updates total_tokens(self.agent).",
        excerptId: "transcript_core"
      }
    ],
    breakpoints: [
      { loc: "simple_agent/tui/app.py:852", watch: "prompt, len(agent.messages), self.stop_requested", why: "Inspect exact pre-turn message list right before conversation_turn() snapshots it." },
      { loc: "simple_agent/tui/transcript.py:106", watch: "list(event.keys()), self.pending_tools, self._turn_usage", why: "Observe every raw Strands callback event shape emitted by the SDK." },
      { loc: "simple_agent/agent.py:24", watch: "resolve_base_url(), os.environ.get('AGENT_PORT')", why: "Verify exact base_url and model params passed to OpenAIModel." }
    ],
    failures: [
      { title: "llama-server not running (Connection Refused)", symptom: "APIConnectionError raised inside agent.invoke_async().", handling: "conversation_turn() rolls back agent.messages; format_invocation_error() renders 'APIConnectionError: Could not connect to model server' without traceback; TUI stays alive.", evidence: "verified" },
      { title: "Inference exceeds 180s timeout", symptom: "TimeoutError / APITimeoutError from OpenAI client (max_retries=0 prevents hidden duplicate retries).", handling: "format_invocation_error() prints 'Provider timed out' and restores prior conversation history.", evidence: "verified" },
      { title: "User presses Esc mid-turn", symptom: "Eager 'escape' binding calls self.interrupt() -> stop_requested=True + task.cancel().", handling: "CancelledError caught inside _respond(); conversation_turn() restores messages; end_turn(stopped=True) prints INTERRUPTED banner.", evidence: "verified" }
    ],
    tests: [
      "tests/test_settings_and_cli.py::BaseUrlTests::test_resolve_base_url_syncs_with_agent_port_and_prefers_explicit_url",
      "tests/test_settings_and_cli.py::CliTests::test_one_shot_cli_formats_errors_and_interrupts_without_traceback",
      "tests/test_tui.py::TranscriptTests::test_tool_lines_stay_inside_the_agent_turn",
      "tests/test_tui.py::AgentTuiTests::test_escape_stops_stream_and_restores_history"
    ]
  },

  {
    id: "wt-memory",
    priority: "CORE PRIORITY #2",
    title: "2. Conversation Memory, Transactional Rollback & /clear",
    subtitle: "How agent.messages lives in memory, why shallow-copy rollback protects multi-tool turns, and how /clear resets state without losing settings.",
    evidence: "verified",
    dataFlow: [
      "agent.messages (Python list owned by Strands Agent)",
      "history = messages.copy() on turn entry",
      "In-turn mutations: user msg -> assistant toolUse -> user toolResult -> assistant reply",
      "Success: keep mutated list | BaseException: messages[:] = history",
      "/clear -> agent_factory() fresh list + apply_agent_settings()"
    ],
    stateTransitions: [
      "M = [m0..mk] (clean history)",
      "SNAPSHOT: history = M.copy()",
      "MUTATING: M grows with partial turn messages",
      "COMMIT (normal exit) -> M retained",
      "ROLLBACK (BaseException) -> M[:] = history (in-place slice preserves object identity)"
    ],
    sequence: {
      actors: ["AgentTui", "conversation_turn", "agent.messages", "Strands Agent", "Transcript"],
      messages: [
        { from: 0, to: 1, label: "enter with conversation_turn(agent.messages)", evidence: "verified" },
        { from: 1, to: 2, label: "history = messages.copy()", evidence: "verified" },
        { from: 0, to: 3, label: "await agent.invoke_async(prompt)", evidence: "verified" },
        { from: 3, to: 2, label: "append(user_msg), append(assistant_toolUse)", evidence: "static" },
        { from: 0, to: 3, label: "Esc -> stop_requested=True; task.cancel()", evidence: "verified" },
        { from: 3, to: 1, label: "raises asyncio.CancelledError (BaseException)", evidence: "verified" },
        { from: 1, to: 2, label: "messages[:] = history (in-place restore)", evidence: "verified" },
        { from: 0, to: 4, label: "end_turn(elapsed, stopped=True)", evidence: "verified" }
      ]
    },
    steps: [
      {
        title: "Step 1 — In-Memory History & Context Window Boundary",
        evidence: "static",
        callChain: ["simple_agent/agent.py:41 -> Agent(...)", "scripts/run_model.py:30 -> --no-context-shift"],
        explanation: "Simple Agent does not persist chat transcripts to disk; each create_agent() call starts with a fresh in-memory agent.messages list. Because llama-server runs with --no-context-shift and a fixed context (-c 8192 default, 4096 on UHD 620), long conversations can exhaust the context window. Users reset via /clear.",
        excerptId: "agent_factory"
      },
      {
        title: "Step 2 — Why conversation_turn Catches BaseException & Uses Slice Assignment",
        evidence: "verified",
        callChain: ["simple_agent/tui/session.py:10 -> conversation_turn(messages)"],
        explanation: "Both KeyboardInterrupt (one-shot / plain mode) and asyncio.CancelledError (TUI Esc interrupt, Python 3.8+) inherit from BaseException, NOT Exception. Catching BaseException guarantees rollback on interrupts as well as HTTP/provider errors. Assigning messages[:] = history mutates the existing list in place so any internal Strands reference to agent.messages sees the restored history.",
        excerptId: "session_turn"
      },
      {
        title: "Step 3 — Distinguishing User Esc Cancellation from App Shutdown",
        evidence: "verified",
        callChain: ["simple_agent/tui/app.py:844 -> interrupt()", "simple_agent/tui/app.py:855 -> except asyncio.CancelledError:"],
        explanation: "When the user presses Esc or Ctrl-C during a turn, interrupt() sets self.stop_requested = True before calling self.task.cancel(). Inside _respond(), if CancelledError arrives with stop_requested == False (e.g. prompt-toolkit shutting down the loop), it re-raises so cancellation propagates cleanly instead of being swallowed.",
        excerptId: "app_submit_respond"
      },
      {
        title: "Step 4 — /clear Swaps Agent Instance & Preserves Header",
        evidence: "verified",
        callChain: ["simple_agent/tui/app.py:823 -> cmd.name == '/clear'", "simple_agent/tui/app.py:216 -> _set_agent()"],
        explanation: "/clear calls self._set_agent(self.agent_factory()) to discard both agent.messages and accumulated event_loop_metrics, immediately reapplies saved agent_name and system_prompt via apply_agent_settings(), rebinds callback_handler = self.transcript, deletes _history.rows[self._header_len:], and refreshes the header.",
        excerptId: "app_submit_respond"
      }
    ],
    breakpoints: [
      { loc: "simple_agent/tui/session.py:16", watch: "len(messages), len(history), messages[len(history):]", why: "Inspect exact partial messages being rolled back on error or Esc interrupt." },
      { loc: "simple_agent/tui/app.py:824", watch: "id(self.agent), self._header_len, len(self._history.rows)", why: "Verify fresh agent object creation and header row preservation on /clear." }
    ],
    failures: [
      { title: "Orphaned toolUse without matching toolResult", symptom: "If a turn were interrupted without rollback, the next API request would send an assistant toolUse with no toolResult, causing OpenAI/Jinja template 400 errors.", handling: "Prevented by conversation_turn() rolling back to the pre-turn snapshot on any BaseException.", evidence: "verified" },
      { title: "Shallow-copy caveat on in-place nested dict mutation", symptom: "messages.copy() is a shallow copy of the list. If a future Strands hook mutates an existing message dict in place, shallow copy would not revert that dict.", handling: "Static analysis note: Strands appends new message dicts per turn rather than mutating old ones, so list.copy() is sufficient today.", evidence: "static" },
      { title: "Context window exhaustion", symptom: "llama-server rejects prompt once history + system prompt + tools > -c tokens (because --no-context-shift is enabled).", handling: "HTTP 400 formatted as 'Provider request failed (HTTP 400)'; conversation_turn rolls back the failed prompt; user runs /clear.", evidence: "assumption" }
    ],
    tests: [
      "tests/test_tui.py::AgentTuiTests::test_escape_stops_stream_and_restores_history",
      "tests/test_tui.py::AgentTuiTests::test_clear_removes_transcript_and_starts_new_conversation",
      "tests/test_settings_and_cli.py::CliTests::test_one_shot_cli_formats_errors_and_interrupts_without_traceback"
    ]
  },

  {
    id: "wt-tools",
    priority: "CORE PRIORITY #3",
    title: "3. Tool Execution & Workspace Security Sandbox",
    subtitle: "How Strands invokes @tool functions and how read_file & search_text enforce workspace confinement, TOCTOU defense, and hard resource budgets.",
    evidence: "verified",
    dataFlow: [
      "Model emits toolUse(name, input) via --jinja template",
      "Strands ToolRegistry dispatches to DEFAULT_TOOLS",
      "Input validation (line range / single-line query)",
      "Path confinement + _is_sensitive_path()",
      "dir_fd O_DIRECTORY|O_NOFOLLOW traversal + O_NONBLOCK fstat S_ISREG",
      "Bounded read / UTF-8 decode / snippet budget -> toolResult string"
    ],
    stateTransitions: [
      "VALIDATE_ARGS",
      "RESOLVE_AND_CONFINE (is_relative_to(root))",
      "SENSITIVE_CHECK (.git, .env, .env.*)",
      "FD_WALK (dir_fd + O_NOFOLLOW + O_PATH)",
      "FSTAT_S_ISREG (blocks FIFOs/dirs/devices)",
      "BUDGETED_READ -> RETURN"
    ],
    sequence: {
      actors: ["Strands Agent", "read_file / search_text", "Path / Policy", "OS dir_fd API", "Workspace FS"],
      messages: [
        { from: 0, to: 1, label: "Invoke @tool with JSON arguments", evidence: "verified" },
        { from: 1, to: 2, label: "Validate range/query, resolve(), check is_relative_to(root)", evidence: "verified" },
        { from: 1, to: 2, label: "_is_sensitive_path(rel_parts)", evidence: "verified" },
        { from: 1, to: 3, label: "os.open('.', O_DIRECTORY|O_NOFOLLOW|O_PATH)", evidence: "verified" },
        { from: 3, to: 4, label: "Step each path component with dir_fd (no symlink follow)", evidence: "verified" },
        { from: 3, to: 4, label: "os.stat(..., follow_symlinks=False) + os.open(O_NONBLOCK|O_NOFOLLOW)", evidence: "verified" },
        { from: 3, to: 1, label: "os.fstat(fd) -> S_ISREG check -> file.read(limit + 1)", evidence: "verified" },
        { from: 1, to: 0, label: "Return UTF-8 string or raise ValueError", evidence: "verified" }
      ]
    },
    steps: [
      {
        title: "Step 1 — Security Constants & Sensitive Path Blocklist",
        evidence: "verified",
        callChain: ["simple_agent/tools/workspace_files.py:24 -> _is_sensitive_path()", "simple_agent/tools/workspace_text.py:7 -> text limits"],
        explanation: "The filesystem and text helpers enforce distinct caps: 4 KiB whole-file / output limit, 1 MiB candidate file limit, 20 search matches, 10,000 scanned entries, 32 MiB total read budget, and max depth 32. _is_sensitive_path() blocks any path containing '.git' as a component, '.env', or '.env.*' unless in ALLOWED_ENV_FILES (.env.example, .env.sample, .env.template).",
        excerptId: "tools_constants"
      },
      {
        title: "Step 2 — TOCTOU-Resistant dir_fd Traversal & FIFO Protection",
        evidence: "verified",
        callChain: ["simple_agent/tools/workspace_files.py:49 -> _open_workspace_file()", "simple_agent/tools/workspace_files.py:32 -> _open_regular_file()"],
        explanation: "Instead of calling open(resolved_path) (vulnerable to symlink swap races and blocking on named pipes/FIFOs), _open_workspace_file() opens '.' with O_DIRECTORY|O_NOFOLLOW|O_PATH (allowing traversal through execute-only 0o111 ancestor directories!), steps component by component via dir_fd, checks lstat S_ISREG, opens with O_RDONLY|O_NONBLOCK|O_NOFOLLOW, and re-verifies S_ISREG via os.fstat(fd).",
        excerptId: "tools_fd_open"
      },
      {
        title: "Step 3 — read_file: Whole-File vs Line-Range Mode",
        evidence: "verified",
        callChain: ["simple_agent/tools/workspace.py:19 -> read_file()", "simple_agent/tools/workspace_files.py:66 -> read_workspace_bytes()", "simple_agent/tools/workspace_text.py:22 -> select_lines()"],
        explanation: "read_file() requires both start_line and end_line or neither, and uses type(x) is int (deliberately rejecting bool since isinstance(True, int) is True!). Whole-file reads cap input at 4 KiB; ranged reads allow candidate files up to 1 MiB, slice splitlines(keepends=True)[start_line-1:end_line], and enforce that the encoded slice fits within 4 KiB.",
        excerptId: "tool_read_file"
      },
      {
        title: "Step 4 — search_text: Deterministic DFS, Budgets & UTF-8 Safe Snippets",
        evidence: "verified",
        callChain: ["simple_agent/tools/workspace.py:35 -> search_text()", "simple_agent/tools/workspace_files.py:128 -> WorkspaceScan.files()", "simple_agent/tools/workspace_text.py:51 -> search_rows()"],
        explanation: "WorkspaceScan sorts directory entries for deterministic results, skips .venv/__pycache__/node_modules and sensitive paths, and skips symlinks. search_rows() skips NUL-byte binaries and non-UTF-8 files, JSON-quotes paths containing ':', '\"', '\\\\', or nonprintable chars (preventing line-break spoofing), and slices UTF-8 snippet windows around the match while reserving space for SEARCH_INCOMPLETE whenever any budget is hit.",
        excerptId: "tool_search_text"
      }
    ],
    breakpoints: [
      { loc: "simple_agent/tools/workspace_files.py:72", watch: "root, resolved, rel_parts", why: "Verify workspace boundary check and symlink target resolution before fd traversal." },
      { loc: "simple_agent/tools/workspace_files.py:53", watch: "name, parent_fd", why: "Step through each dir_fd hop during O_NOFOLLOW traversal." },
      { loc: "simple_agent/tools/workspace_text.py:69", watch: "result_left, available, len(rows)", why: "Inspect the output budget on each match." },
      { loc: "simple_agent/tools/workspace_files.py:152", watch: "read_left, self._entries_left", why: "Inspect the scan budgets." }
    ],
    failures: [
      { title: "Path traversal or symlink escape", symptom: "read_file('../secret.txt') or symlink pointing outside workspace or to .env.", handling: "Blocked by resolved.is_relative_to(root) or _is_sensitive_path(), raising ValueError (surfaced to model as toolResult error).", evidence: "verified" },
      { title: "Named pipe (FIFO) DoS attempt", symptom: "read_file('pipe.fifo') would hang indefinitely on standard open().", handling: "Blocked before read by lstat S_ISREG check + O_NONBLOCK + fstat S_ISREG check.", evidence: "verified" },
      { title: "Large repository search exhaustion", symptom: ">10,000 entries, depth > 32, >32 MiB read, >20 matches, or >4 KiB output.", handling: "Terminates cleanly within budget and appends '[Search incomplete. Some files or matches may have been skipped.]'.", evidence: "verified" }
    ],
    tests: [
      "tests/test_tools.py::ToolTests (3 tests)",
      "tests/test_tools.py::WorkspaceSearchTests (12 tests — including 0o111 search-only dirs, FIFOs, multi-byte emoji snippets, and depth 40)"
    ]
  },

  {
    id: "wt-persistence",
    priority: "CORE PRIORITY #4",
    title: "4. Settings & Preferences Persistence",
    subtitle: "XDG config resolution, fault-tolerant JSON loading, atomic tempfile+os.replace writes, and live /settings & /pet updates.",
    evidence: "verified",
    dataFlow: [
      "XDG_CONFIG_HOME or ~/.config -> simple-agent/settings.json",
      "_read_settings() -> dict (or {} on missing/corrupt/non-dict)",
      "data.update(updates) -> merge without clobbering unrelated keys",
      "tempfile.mkstemp(dir=target.parent) -> write -> os.replace(tmp, target)",
      "apply_agent_settings(agent) -> sets agent.name & agent.system_prompt"
    ],
    stateTransitions: [
      "LOAD_EXISTING (or {})",
      "MERGE_UPDATES",
      "MKDIR_PARENTS",
      "WRITE_TMP_SAME_DIR",
      "ATOMIC_OS_REPLACE",
      "FINALLY_UNLINK_MISSING_OK"
    ],
    sequence: {
      actors: ["User (/settings or --pet)", "AgentTui / CLI", "settings.py", "Filesystem", "Strands Agent"],
      messages: [
        { from: 0, to: 1, label: "Ctrl-S in /settings (or --pet moth)", evidence: "verified" },
        { from: 1, to: 2, label: "normalize_agent_name() / normalize_pet()", evidence: "verified" },
        { from: 1, to: 2, label: "save_settings(updates, config_path)", evidence: "verified" },
        { from: 2, to: 3, label: "_read_settings() -> merge -> mkstemp() in same dir", evidence: "verified" },
        { from: 2, to: 3, label: "os.replace(tmp_name, target)", evidence: "verified" },
        { from: 1, to: 4, label: "agent.name = name; agent.system_prompt = prompt or None", evidence: "verified" },
        { from: 1, to: 1, label: "_refresh_header() (keeps current conversation)", evidence: "verified" }
      ]
    },
    steps: [
      {
        title: "Step 1 — XDG Path Resolution & Fault-Tolerant Read",
        evidence: "verified",
        callChain: ["simple_agent/settings.py:12 -> settings_path()", "simple_agent/settings.py:19 -> _read_settings()", "simple_agent/settings.py:27 -> load_settings()"],
        explanation: "settings_path() respects XDG_CONFIG_HOME (expanding ~) and defaults to ~/.config/simple-agent/settings.json. _read_settings() returns {} if the file is missing, invalid JSON, or not a JSON object (e.g. a JSON array). load_settings() additionally catches OSError so startup never crashes on unreadable config.",
        excerptId: "settings_io"
      },
      {
        title: "Step 2 — Atomic Merge-and-Replace Writes",
        evidence: "verified",
        callChain: ["simple_agent/settings.py:34 -> save_settings(updates, path)"],
        explanation: "save_settings() reads existing keys first, merges updates (preserving unrelated keys like mouse_scroll_speed or pet), creates parent directories, writes formatted JSON to a temporary file in the SAME directory (ensuring same-filesystem atomic rename), calls os.replace(tmp_name, target), and cleans up tmp_name in a finally block.",
        excerptId: "settings_io"
      },
      {
        title: "Step 3 — Name Sanitization & Empty Prompt Semantics",
        evidence: "verified",
        callChain: ["simple_agent/settings.py:50 -> normalize_agent_name()", "simple_agent/settings.py:60 -> apply_agent_settings()"],
        explanation: "normalize_agent_name() strips whitespace and rejects empty strings or any character in Unicode categories Cc (control, including \\n, \\t, \\x1b), Cs (surrogate), Zl (line sep), or Zp (paragraph sep). In apply_agent_settings(), an empty string system_prompt explicitly sets agent.system_prompt = None (disabling it), while a missing key leaves the built-in SYSTEM_PROMPT untouched.",
        excerptId: "settings_apply"
      },
      {
        title: "Step 4 — In-TUI /settings Modal & Live Header Refresh",
        evidence: "verified",
        callChain: ["simple_agent/tui/app.py:300 -> _open_settings()", "simple_agent/tui/app.py:313 -> _save_agent_settings()", "simple_agent/tui/app.py:331 -> _refresh_header()"],
        explanation: "_open_settings() populates single-line _name_buffer and multiline _system_prompt_buffer and disables prompt-toolkit mouse_support while editing so terminal text selection works. On Ctrl-S, _save_agent_settings() validates, persists, mutates self.agent in place (preserving conversation history!), and updates the header box in place via _history.rows[:self._header_len] = rows.",
        excerptId: "app_modals"
      }
    ],
    breakpoints: [
      { loc: "simple_agent/settings.py:45", watch: "tmp_name, target, data", why: "Inspect atomic temp file right before os.replace() swaps it into settings.json." },
      { loc: "simple_agent/tui/app.py:325", watch: "self.agent.name, self.agent.system_prompt", why: "Confirm live mutation applies to the next turn without resetting agent.messages." }
    ],
    failures: [
      { title: "Corrupt or non-dict settings.json", symptom: "User hand-edits settings.json with broken syntax or a JSON list.", handling: "_read_settings() falls back to {} so app boots normally; next save overwrites cleanly.", evidence: "verified" },
      { title: "Read-only config directory (OSError)", symptom: "save_settings() raises PermissionError/OSError.", handling: "CLI prints formatted stderr error and exits 1; /settings shows inline _settings_error without closing the modal; /pet prints transcript error.", evidence: "verified" }
    ],
    tests: [
      "tests/test_settings_and_cli.py::SettingsTests (2 tests)",
      "tests/test_settings_and_cli.py::CliTests::test_one_shot_cli_applies_settings_and_persists_pet",
      "tests/test_tui.py::PetTests::test_persistence_roundtrip_preserves_other_keys_and_handles_corrupt_files",
      "tests/test_tui.py::AgentTuiTests::test_settings_editor_updates_the_next_turn_and_persists_after_clear"
    ]
  },

  {
    id: "wt-tui-markdown",
    priority: "SUBSYSTEM #5",
    title: "5. Streaming Markdown Renderer & Codex-Style Scrollable TUI",
    subtitle: "How StreamCell achieves zero-flicker incremental commits, split-ANSI sanitization, theme-aware bold red, GFM tables, and sticky-follow scrolling.",
    evidence: "verified",
    dataFlow: [
      "Raw model chunk -> INCOMPLETE_ANSI holdback (<=256B) -> sanitize_text()",
      "Split on '\\n': complete lines -> _commit_markdown_line() | partial -> self.line",
      "2-line table lookahead (_table_lines) & CommonMark fence state",
      "parse_inline() PUA atom masking -> bold_markdown_style() -> wrap_spans()",
      "TranscriptControl: committed rows + side-effect-free tail() + first_line scroll pin"
    ],
    stateTransitions: [
      "NORMAL_MD",
      "IN_FENCE (char, min_len)",
      "TABLE_CANDIDATE (len(_table_lines)==1)",
      "TABLE_ACTIVE (len(_table_lines)>=2)",
      "FLUSH_TABLE -> NORMAL_MD"
    ],
    sequence: {
      actors: ["StreamCell.push", "Sanitizer", "Markdown Engine", "TranscriptControl", "AgentTui Scroll"],
      messages: [
        { from: 0, to: 1, label: "Hold trailing incomplete ANSI/OSC; sanitize_text()", evidence: "verified" },
        { from: 0, to: 2, label: "Complete lines -> fence / table / render_markdown_line()", evidence: "verified" },
        { from: 2, to: 3, label: "Emit immutable ANSI rows into _history.rows", evidence: "verified" },
        { from: 3, to: 0, label: "On paint: create_content() calls tail() (non-mutating)", evidence: "verified" },
        { from: 4, to: 3, label: "Wheel/PgUp sets first_line=target; bottom sets first_line=None", evidence: "verified" }
      ]
    },
    steps: [
      {
        title: "Step 1 — Split-Chunk ANSI/OSC Escape Buffering & Sanitization",
        evidence: "verified",
        callChain: ["simple_agent/tui/rendering.py:429 -> StreamCell.push()", "simple_agent/tui/rendering.py:100 -> sanitize_text()"],
        explanation: "Untrusted model/tool output can contain terminal escape sequences split across streaming chunks (e.g. '\\x1b[' then '31m'). push() matches INCOMPLETE_ANSI at the end of each chunk (capped at MAX_ESCAPE_BUFFER=256 bytes) and holds it in self._pending_escape until the next chunk completes it, then strips all CSI/OSC/DCS/C0 controls.",
        excerptId: "rendering_streamcell"
      },
      {
        title: "Step 2 — Two-Pass Inline Markdown & Theme-Aware Bold Red",
        evidence: "verified",
        callChain: ["simple_agent/tui/markdown.py:196 -> parse_inline()", "simple_agent/tui/markdown.py:56 -> bold_markdown_style()", "simple_agent/tui/markdown.py:83 -> combine_sgr()"],
        explanation: "parse_inline() first masks backslash escapes and backtick code spans into Private-Use-Area placeholders (\\ue000idx\\ue001) so asterisks/underscores inside code never trigger formatting. Pass 2 recursively parses links, ***bold italic***, **bold**, *italic*, and ~~strike~~. Commit 7fb39a2 styled bold Markdown in theme-aware red: 1;38;5;174 on dark terminals and 1;38;5;124 when COLORFGBG indicates a light background.",
        excerptId: "markdown_parse_inline"
      },
      {
        title: "Step 3 — Side-Effect-Free tail() Preview & Table Lookahead",
        evidence: "verified",
        callChain: ["simple_agent/tui/rendering.py:459 -> StreamCell.tail()", "simple_agent/tui/markdown.py:635 -> _allocate_column_widths()"],
        explanation: "A GFM pipe table cannot be confirmed until line 2 matches parse_table_alignments(). StreamCell buffers line 1 in _table_lines and immediately flushes it as normal Markdown if line 2's partial prefix fails can_be_table_delimiter_prefix(). tail() copies started, blank_rows, fence, and list stacks into locals so rendering the live preview never mutates committed state.",
        excerptId: "rendering_streamcell_tail"
      },
      {
        title: "Step 4 — Sticky-Follow Scrolling, Fractional Wheel & Ctrl-T Pager",
        evidence: "verified",
        callChain: ["simple_agent/tui/app.py:98 -> TranscriptControl", "simple_agent/tui/app.py:577 -> _scroll_wheel()", "simple_agent/tui/app.py:586 -> _scroll_lines()"],
        explanation: "When _history.first_line is None, TranscriptControl places the cursor on the last row so prompt-toolkit auto-follows live output. Scrolling up sets first_line = target and vertical_scroll = target, pausing auto-follow and showing '↑ scrolled' in the footer. _scroll_wheel() accumulates fractional mouse_scroll_speed in _scroll_remainder (resetting on direction reversal). Ctrl-T toggles _in_pager with vim keys (j/k/g/G/Ctrl-U/Ctrl-D) while any running turn continues in the background.",
        excerptId: "app_scroll"
      }
    ],
    breakpoints: [
      { loc: "simple_agent/tui/rendering.py:434", watch: "raw, self._pending_escape, self._table_lines", why: "Inspect split-ANSI holdback and table lookahead state on each chunk." },
      { loc: "simple_agent/tui/app.py:586", watch: "delta, first, last, info.content_height, self._history.first_line", why: "Trace sticky-follow transition between pinned int and live None." }
    ],
    failures: [
      { title: "Terminal too narrow for GFM table", symptom: "width < 4 * col_count + 1.", handling: "render_table() automatically switches to stacked '**Header**: value' card layout separated by horizontal rules.", evidence: "verified" },
      { title: "Terminal resized mid-session", symptom: "Header box width becomes stale.", handling: "TranscriptControl.create_content() calls on_width_change(width) -> _sync_width() -> _refresh_header(width=width, invalidate=False) to reflow the header in place.", evidence: "verified" }
    ],
    tests: [
      "tests/test_tui.py::TranscriptTests (all 9 tests)",
      "tests/test_tui.py::AgentTuiTests::test_fullscreen_mouse_wheel_sticky_follow_and_jump_shortcuts",
      "tests/test_tui.py::AgentTuiTests::test_ctrl_t_transcript_overlay_supports_vim_keys_and_preserves_running_turn",
      "tests/test_tui.py::AgentTuiTests::test_header_reflows_automatically_when_terminal_width_changes"
    ]
  },

  {
    id: "wt-runtime",
    priority: "SUBSYSTEM #6",
    title: "6. Local Inference Launcher & Hardware Profiles",
    subtitle: "How scripts/run_model.py configures llama-server for default Vulkan vs Intel UHD 620 CPU/Vulkan profiles, probes devices, and hands off via os.execve.",
    evidence: "verified",
    dataFlow: [
      "CLI --profile (default | uhd620-cpu | uhd620-vulkan) + --dry-run",
      "Environment overrides (DICTATION_ROOT, AGENT_LLAMA_BIN, AGENT_MODEL, AGENT_PORT, ...)",
      "model_command(env, profile) -> argv list",
      "Asset existence check + Vulkan --list-devices probe (except uhd620-cpu)",
      "os.execve(binary, command, env) -> replaces Python process with llama-server"
    ],
    stateTransitions: [
      "PARSE_ARGS",
      "PREPARE_ENV (GGML_VK_PREFER_HOST_MEMORY / pop LLAMA_ARG_DEVICE)",
      "BUILD_COMMAND",
      "DRY_RUN_EXIT | VALIDATE_FILES",
      "VULKAN_PROBE (skipped for uhd620-cpu)",
      "OS_EXECVE"
    ],
    sequence: {
      actors: ["Developer", "scripts/run_model.py", "llama-server --list-devices", "llama-server (execve)", "simple_agent/agent.py"],
      messages: [
        { from: 0, to: 1, label: "uv run python scripts/run_model.py [--profile ...]", evidence: "verified" },
        { from: 1, to: 1, label: "model_command(env, profile) + Path.is_file() checks", evidence: "verified" },
        { from: 1, to: 2, label: "subprocess.run([bin, '--list-devices'], timeout=30)", evidence: "verified" },
        { from: 2, to: 1, label: "stdout matched against ^\\s*Vulkan\\d+:", evidence: "verified" },
        { from: 1, to: 3, label: "os.execve(bin, cmd, env) — serves --alias gemma-4-e4b", evidence: "verified" },
        { from: 4, to: 3, label: "resolve_base_url() connects to 127.0.0.1:${AGENT_PORT:-8088}/v1", evidence: "static" }
      ]
    },
    steps: [
      {
        title: "Step 1 — Profile Matrix & Shared Alias Contract",
        evidence: "verified",
        callChain: ["scripts/run_model.py:11 -> model_command(env, profile)"],
        explanation: "All profiles serve the model under --alias gemma-4-e4b so simple_agent/agent.py never needs to change model_id. 'default' targets Gemma 4 E4B Q4_0 with -ngl 99, -c 8192, --flash-attn on, q8_0 KV cache, and GGML_VK_PREFER_HOST_MEMORY=1. 'uhd620-cpu' and 'uhd620-vulkan' target Gemma 4 E2B Q4_0 with -c 4096, f16 KV cache, and --flash-attn auto.",
        excerptId: "runtime_launcher"
      },
      {
        title: "Step 2 — Why uhd620-cpu Strips LLAMA_ARG_DEVICE",
        evidence: "verified",
        callChain: ["scripts/run_model.py:49-51 -> env.pop('LLAMA_ARG_DEVICE', None)"],
        explanation: "llama.cpp validates LLAMA_ARG_DEVICE from the environment before applying CLI --device none. Stripping LLAMA_ARG_DEVICE prevents an inherited Vulkan device variable from breaking CPU-only runs, and forces -ngl 0 regardless of AGENT_GPU_LAYERS.",
        excerptId: "runtime_launcher"
      },
      {
        title: "Step 3 — Fail-Fast Vulkan Probe & os.execve Handoff",
        evidence: "verified",
        callChain: ["scripts/run_model.py:58-69 -> main()"],
        explanation: "Vulkan profiles intentionally refuse silent CPU fallback: they run [binary, '--list-devices'] (30s timeout) and require a regex match for Vulkan0+. Finally, os.execve() replaces the Python wrapper process directly with llama-server so Ctrl-C signals go straight to llama-server with zero wrapper overhead.",
        excerptId: "runtime_launcher"
      }
    ],
    breakpoints: [
      { loc: "scripts/run_model.py:52", watch: "args.profile, command, env.get('GGML_VK_PREFER_HOST_MEMORY')", why: "Inspect exact launch flags before dry-run print or execve." }
    ],
    failures: [
      { title: "Missing llama-server binary or GGUF weights", symptom: "Path(path).is_file() returns False.", handling: "parser.error() exits with instructions to set AGENT_LLAMA_BIN / AGENT_MODEL or provision dictation assets. Never downloads weights automatically.", evidence: "verified" },
      { title: "No Vulkan device detected", symptom: "--list-devices returns non-zero or lacks 'VulkanN:'.", handling: "parser.error('No Vulkan device detected. Check Vulkan drivers and /dev/dri access.') — no silent CPU fallback.", evidence: "verified" }
    ],
    tests: [
      "tests/test_runtime.py::RuntimeTests (all 5 tests)"
    ]
  }
];
