// Multi-level C4 architecture model and searchable feature inventory.
// Every code reference maps to verbatim slices in window.ATLAS_EXCERPTS.

window.ATLAS_C4 = {
  l1: {
    title: "Level 1 — System Context",
    subtitle: "How a developer interacts with Simple Agent and its local execution boundaries (no cloud APIs).",
    nodes: [
      {
        id: "user", kind: "person", label: "Developer / User", tech: "Interactive TTY or Piped stdin",
        x: 60, y: 120, w: 190, h: 86,
        evidence: "verified",
        summary: "Drives Simple Agent via one-shot CLI prompt, full-screen interactive TUI, or piped stdin/stdout.",
        files: ["main.py:1-6", "simple_agent/cli.py:28-73"],
        excerpts: ["entry_main", "cli_run"],
        tests: ["tests/test_settings_and_cli.py::CliTests", "tests/test_tui.py::AgentTuiTests"]
      },
      {
        id: "simple_agent", kind: "system", label: "Simple Agent", tech: "Python 3.12 · Strands · prompt-toolkit",
        x: 340, y: 110, w: 230, h: 106,
        evidence: "verified",
        summary: "Local CLI/TUI agent application. Wires Strands Agent + OpenAIModel to a local llama.cpp endpoint, exposes sandboxed workspace tools, manages turn rollback, and renders streaming Markdown.",
        files: ["simple_agent/agent.py:1-46", "simple_agent/cli.py:1-73", "simple_agent/tui/app.py:151-882"],
        excerpts: ["agent_factory", "cli_run"],
        tests: ["All 50 unit tests across tests/test_*.py"]
      },
      {
        id: "llama_server", kind: "external", label: "Local llama-server", tech: "llama.cpp · Vulkan / CPU · HTTP :8088",
        x: 660, y: 40, w: 220, h: 88,
        evidence: "assumption",
        summary: "External local inference binary launched by scripts/run_model.py. Serves Gemma 4 GGUF under OpenAI-compatible alias 'gemma-4-e4b' with --jinja tool-call templating and --no-context-shift.",
        files: ["scripts/run_model.py:11-73"],
        excerpts: ["runtime_launcher"],
        tests: ["tests/test_runtime.py::RuntimeTests (command construction & mocked execve verified; live GPU server not started during unit tests)"]
      },
      {
        id: "workspace_fs", kind: "external", label: "Workspace Filesystem", tech: "Current Working Directory (read-only tools)",
        x: 660, y: 160, w: 220, h: 84,
        evidence: "verified",
        summary: "Project files inspected by read_file and search_text via TOCTOU-resistant dir_fd traversal. Excludes .git, .env, .env.* (except allowlisted examples), symlinks, and non-regular files.",
        files: ["simple_agent/tools.py:14-255"],
        excerpts: ["tools_constants", "tools_fd_open"],
        tests: ["tests/test_tools.py::ToolTests", "tests/test_tools.py::WorkspaceSearchTests"]
      },
      {
        id: "xdg_config", kind: "external", label: "XDG User Config", tech: "~/.config/simple-agent/settings.json",
        x: 340, y: 270, w: 230, h: 78,
        evidence: "verified",
        summary: "Atomic JSON preference store shared across CLI, plain mode, and full-screen TUI. Persists agent_name, system_prompt, pet, and mouse_scroll_speed.",
        files: ["simple_agent/settings.py:12-66"],
        excerpts: ["settings_io", "settings_apply"],
        tests: ["tests/test_settings_and_cli.py::SettingsTests", "tests/test_tui.py::PetTests"]
      }
    ],
    edges: [
      { from: "user", to: "simple_agent", label: "Prompts, slash commands, keys/mouse", evidence: "verified" },
      { from: "simple_agent", to: "llama_server", label: "POST /v1/chat/completions (streaming SSE)", evidence: "assumption" },
      { from: "simple_agent", to: "workspace_fs", label: "dir_fd O_NOFOLLOW reads & bounded DFS", evidence: "verified" },
      { from: "simple_agent", to: "xdg_config", label: "Read / atomic tempfile + os.replace", evidence: "verified" }
    ]
  },

  l2: {
    title: "Level 2 — Containers",
    subtitle: "Runtime processes and primary logical subsystems inside Simple Agent.",
    nodes: [
      {
        id: "cli_entry", kind: "container", label: "CLI Dispatcher", tech: "main.py · simple_agent/cli.py",
        x: 40, y: 120, w: 190, h: 86,
        evidence: "verified",
        summary: "Parses optional positional prompt and --pet flag. Selects one-shot mode, full-screen AgentTui (when TTY & TERM != dumb), or line-oriented run_plain fallback.",
        files: ["main.py:1-6", "simple_agent/cli.py:28-73"],
        excerpts: ["cli_run"],
        tests: ["tests/test_settings_and_cli.py::CliTests"]
      },
      {
        id: "tui_container", kind: "container", label: "Terminal UI (Full-Screen & Plain)", tech: "simple_agent/tui/*",
        x: 280, y: 40, w: 230, h: 92,
        evidence: "verified",
        summary: "Owns prompt-toolkit Application, Codex-style sticky-follow scrolling, Ctrl-T transcript overlay, slash commands, pet picker, settings editor, and streaming Markdown rendering.",
        files: ["simple_agent/tui/app.py:151-882", "simple_agent/tui/plain.py:15-85", "simple_agent/tui/transcript.py:41-158"],
        excerpts: ["app_submit_respond", "plain_loop"],
        tests: ["tests/test_tui.py (25 tests)"]
      },
      {
        id: "agent_core", kind: "container", label: "Agent & Tool Loop", tech: "agent.py · tools.py · prompts.py · Strands SDK",
        x: 280, y: 185, w: 230, h: 92,
        evidence: "verified",
        summary: "create_agent() binds OpenAIModel, SYSTEM_PROMPT, and DEFAULT_TOOLS into a Strands Agent. Strands owns the multi-step inference/tool-call loop and emits callback events to Transcript.",
        files: ["simple_agent/agent.py:13-46", "simple_agent/tools.py:74-255", "simple_agent/prompts.py:3-10"],
        excerpts: ["agent_factory", "system_prompt"],
        tests: ["tests/test_settings_and_cli.py::BaseUrlTests", "tests/test_tools.py (15 tests)"]
      },
      {
        id: "settings_store", kind: "container", label: "Settings Persistence", tech: "simple_agent/settings.py",
        x: 575, y: 185, w: 205, h: 86,
        evidence: "verified",
        summary: "Resolves XDG_CONFIG_HOME/simple-agent/settings.json, merges partial updates, writes via mkstemp + os.replace, and applies agent_name and system_prompt overrides.",
        files: ["simple_agent/settings.py:12-66"],
        excerpts: ["settings_io", "settings_apply"],
        tests: ["tests/test_settings_and_cli.py::SettingsTests", "tests/test_tui.py::PetTests::test_persistence_roundtrip_preserves_other_keys_and_handles_corrupt_files"]
      },
      {
        id: "model_launcher", kind: "external", label: "Model Server Launcher", tech: "scripts/run_model.py -> llama-server",
        x: 575, y: 40, w: 205, h: 86,
        evidence: "verified",
        summary: "Standalone launcher building hardware-tuned llama-server flags for default (E4B Vulkan), uhd620-cpu (E2B CPU), and uhd620-vulkan (E2B 8 layers), probing Vulkan devices before os.execve.",
        files: ["scripts/run_model.py:11-73"],
        excerpts: ["runtime_launcher"],
        tests: ["tests/test_runtime.py::RuntimeTests (5 tests)"]
      }
    ],
    edges: [
      { from: "cli_entry", to: "tui_container", label: "Interactive TTY -> AgentTui.run() / Pipe -> run_plain()", evidence: "verified" },
      { from: "cli_entry", to: "agent_core", label: "One-shot prompt -> agent(prompt) inside conversation_turn", evidence: "verified" },
      { from: "tui_container", to: "agent_core", label: "await agent.invoke_async(prompt) + callback_handler=Transcript", evidence: "verified" },
      { from: "tui_container", to: "settings_store", label: "Load/save pet, agent_name, system_prompt, mouse_scroll_speed", evidence: "verified" },
      { from: "agent_core", to: "model_launcher", label: "HTTP OpenAI API via resolve_base_url() (:8088/v1)", evidence: "static" }
    ]
  },

  l3: {
    title: "Level 3 — Components",
    subtitle: "Module-level breakdown across simple_agent/ and simple_agent/tui/.",
    nodes: [
      {
        id: "comp_app", kind: "component", label: "tui/app.py", tech: "AgentTui · TranscriptControl · _WheelFallbackWindow",
        x: 30, y: 30, w: 210, h: 78,
        evidence: "verified",
        summary: "Full-screen prompt-toolkit layout, modal overlays (Ctrl-T pager, pet picker, settings editor), keybindings, sticky-follow scroll engine, and async turn lifecycle.",
        files: ["simple_agent/tui/app.py:58-882"],
        excerpts: ["app_wheel_and_control", "app_scroll", "app_submit_respond"],
        tests: ["tests/test_tui.py::AgentTuiTests (8 async tests)"]
      },
      {
        id: "comp_transcript", kind: "component", label: "tui/transcript.py", tech: "Transcript · format_invocation_error",
        x: 270, y: 30, w: 205, h: 78,
        evidence: "verified",
        summary: "Strands callback handler. Routes reasoningText and data chunks to StreamCell, tracks pending_tools by toolUseId, commits tool call+result cells, accumulates turn token usage, and sanitizes errors.",
        files: ["simple_agent/tui/transcript.py:22-158"],
        excerpts: ["transcript_errors", "transcript_core"],
        tests: ["tests/test_tui.py::TranscriptTests"]
      },
      {
        id: "comp_rendering", kind: "component", label: "tui/rendering.py", tech: "StreamCell · sanitize_text · cells",
        x: 505, y: 30, w: 205, h: 78,
        evidence: "verified",
        summary: "ANSI/OSC sanitizer with split-chunk buffer, monotonic word wrapper, header/user/tool/error/usage cell builders, and StreamCell incremental committer with side-effect-free tail() preview.",
        files: ["simple_agent/tui/rendering.py:81-574"],
        excerpts: ["rendering_sanitize", "rendering_streamcell", "rendering_streamcell_tail"],
        tests: ["tests/test_tui.py::TranscriptTests"]
      },
      {
        id: "comp_markdown", kind: "component", label: "tui/markdown.py", tech: "parse_inline · render_markdown_line · render_table",
        x: 740, y: 30, w: 205, h: 78,
        evidence: "verified",
        summary: "Streaming-compatible Markdown parser: two-pass PUA atom masking for escapes/backticks, theme-aware bold red (bold_markdown_style), nested lists/tasks/quotes, CommonMark fences, and proportional GFM tables.",
        files: ["simple_agent/tui/markdown.py:1-796"],
        excerpts: ["markdown_inline", "markdown_parse_inline", "markdown_table_alloc"],
        tests: ["tests/test_tui.py::TranscriptTests (4 markdown tests)"]
      },
      {
        id: "comp_session", kind: "component", label: "tui/session.py", tech: "conversation_turn · session_info · total_tokens",
        x: 30, y: 145, w: 210, h: 74,
        evidence: "verified",
        summary: "Transactional shallow-copy rollback context manager for agent.messages on BaseException, plus header/footer metadata extraction.",
        files: ["simple_agent/tui/session.py:10-63"],
        excerpts: ["session_turn"],
        tests: ["tests/test_settings_and_cli.py::CliTests", "tests/test_tui.py::AgentTuiTests::test_escape_stops_stream_and_restores_history"]
      },
      {
        id: "comp_commands", kind: "component", label: "tui/commands.py & pets.py", tech: "parse_slash_command · pet_rows",
        x: 270, y: 145, w: 205, h: 74,
        evidence: "verified",
        summary: "Local slash command parser (/clear, /exit, /pet, /settings, /tools, /status) with unambiguous prefix resolution, plus 15 half-block RGB/256-color companion pets.",
        files: ["simple_agent/tui/commands.py:11-90", "simple_agent/tui/pets.py:521-603"],
        excerpts: ["commands_parser", "pets_render"],
        tests: ["tests/test_tui.py::PetTests", "tests/test_tui.py::PlainModePetTests"]
      },
      {
        id: "comp_agent", kind: "component", label: "agent.py & prompts.py", tech: "create_agent · resolve_base_url · SYSTEM_PROMPT",
        x: 505, y: 145, w: 205, h: 74,
        evidence: "verified",
        summary: "Builds Strands Agent with OpenAIModel (timeout=180s, max_retries=0, max_tokens=2048, temp=0.2, cache_prompt=True, enable_thinking=False) and DEFAULT_TOOLS.",
        files: ["simple_agent/agent.py:13-46", "simple_agent/prompts.py:3-10"],
        excerpts: ["agent_factory", "system_prompt"],
        tests: ["tests/test_settings_and_cli.py::BaseUrlTests"]
      },
      {
        id: "comp_tools", kind: "component", label: "tools.py", tech: "current_time · read_file · search_text",
        x: 740, y: 145, w: 205, h: 74,
        evidence: "verified",
        summary: "Strands @tool functions with strict workspace confinement, dir_fd O_NOFOLLOW traversal, sensitive file blocklist, and hard byte/entry/depth budgets.",
        files: ["simple_agent/tools.py:14-255"],
        excerpts: ["tools_constants", "tool_read_file", "tool_search_text"],
        tests: ["tests/test_tools.py (15 tests)"]
      },
      {
        id: "comp_settings", kind: "component", label: "settings.py & terminal.py", tech: "save_settings · apply_agent_settings · use_color",
        x: 270, y: 255, w: 205, h: 70,
        evidence: "verified",
        summary: "Atomic JSON settings I/O and terminal capability probes (TTY, NO_COLOR, COLORTERM truecolor, COLORFGBG light background).",
        files: ["simple_agent/settings.py:12-66", "simple_agent/tui/terminal.py:7-30"],
        excerpts: ["settings_io", "terminal_caps"],
        tests: ["tests/test_settings_and_cli.py::SettingsTests"]
      },
      {
        id: "comp_plain", kind: "component", label: "tui/plain.py & cli.py", tech: "run_cli · run_plain",
        x: 505, y: 255, w: 205, h: 70,
        evidence: "verified",
        summary: "Non-fullscreen entrypoints sharing Transcript, conversation_turn, parse_slash_command, and apply_agent_settings.",
        files: ["simple_agent/cli.py:28-73", "simple_agent/tui/plain.py:15-85"],
        excerpts: ["cli_run", "plain_loop"],
        tests: ["tests/test_settings_and_cli.py::CliTests", "tests/test_tui.py::PlainModePetTests"]
      }
    ],
    edges: [
      { from: "comp_app", to: "comp_transcript", label: "agent.callback_handler = self.transcript; _emit() -> _history.rows", evidence: "verified" },
      { from: "comp_transcript", to: "comp_rendering", label: "StreamCell.push()/tail()/finish() & cell builders", evidence: "verified" },
      { from: "comp_rendering", to: "comp_markdown", label: "render_markdown_line(), render_table(), fence_transition()", evidence: "verified" },
      { from: "comp_app", to: "comp_session", label: "with conversation_turn(agent.messages):", evidence: "verified" },
      { from: "comp_app", to: "comp_commands", label: "parse_slash_command() & pet picker", evidence: "verified" },
      { from: "comp_agent", to: "comp_tools", label: "tools=list(DEFAULT_TOOLS)", evidence: "verified" },
      { from: "comp_app", to: "comp_settings", label: "apply_agent_settings() / save_settings()", evidence: "verified" },
      { from: "comp_plain", to: "comp_transcript", label: "Transcript(write_rows, ...)", evidence: "verified" }
    ]
  },

  l4: {
    title: "Level 4 — Code Topology (Key Classes & Data Structures)",
    subtitle: "Critical runtime types, mutable state ownership, and invariants.",
    nodes: [
      {
        id: "cls_agent_tui", kind: "component", label: "class AgentTui", tech: "simple_agent/tui/app.py:151",
        x: 30, y: 30, w: 225, h: 98,
        evidence: "verified",
        summary: "State: agent, task (asyncio.Task), turn_started, stop_requested, _in_pager, _pet_picker_index, _editing_settings, _scroll_remainder, _header_len, _header_width.",
        files: ["simple_agent/tui/app.py:151-242", "simple_agent/tui/app.py:807-882"],
        excerpts: ["app_init", "app_submit_respond"],
        tests: ["tests/test_tui.py::AgentTuiTests"]
      },
      {
        id: "cls_transcript_ctrl", kind: "component", label: "class TranscriptControl(UIControl)", tech: "simple_agent/tui/app.py:98",
        x: 290, y: 30, w: 235, h: 98,
        evidence: "verified",
        summary: "State: rows (immutable committed ANSI lines), first_line (None = sticky bottom follow; int = pinned scroll row). Uses @cache get_line() with ANSI() parsing inside create_content().",
        files: ["simple_agent/tui/app.py:98-149"],
        excerpts: ["app_wheel_and_control"],
        tests: ["tests/test_tui.py::AgentTuiTests::test_fullscreen_mouse_wheel_sticky_follow_and_jump_shortcuts"]
      },
      {
        id: "cls_transcript", kind: "component", label: "class Transcript", tech: "simple_agent/tui/transcript.py:41",
        x: 560, y: 30, w: 225, h: 98,
        evidence: "verified",
        summary: "State: stream (StreamCell|None), stream_kind, _stream_opened, pending_tools (dict[toolUseId, (name, input)]), tool_calls, _turn_usage. Callable Strands callback_handler.",
        files: ["simple_agent/tui/transcript.py:41-158"],
        excerpts: ["transcript_core"],
        tests: ["tests/test_tui.py::TranscriptTests"]
      },
      {
        id: "cls_streamcell", kind: "component", label: "class StreamCell", tech: "simple_agent/tui/rendering.py:313",
        x: 560, y: 165, w: 225, h: 102,
        evidence: "verified",
        summary: "State: line, committed, started, blank_rows, fence ((char, len)|None), _list_indents, _quote_list_indents, _table_lines, _pending_escape. tail() copies state to preview without mutating.",
        files: ["simple_agent/tui/rendering.py:313-562"],
        excerpts: ["rendering_streamcell", "rendering_streamcell_tail"],
        tests: ["tests/test_tui.py::TranscriptTests::test_markdown_streaming_char_by_char_matches_batch_and_previews_live_tail"]
      },
      {
        id: "fn_conv_turn", kind: "component", label: "conversation_turn(messages)", tech: "simple_agent/tui/session.py:10",
        x: 30, y: 165, w: 225, h: 94,
        evidence: "verified",
        summary: "Context manager snapshotting history = messages.copy(). On any BaseException (including KeyboardInterrupt & asyncio.CancelledError), slices messages[:] = history in place before re-raising.",
        files: ["simple_agent/tui/session.py:10-19"],
        excerpts: ["session_turn"],
        tests: ["tests/test_tui.py::AgentTuiTests::test_escape_stops_stream_and_restores_history", "tests/test_settings_and_cli.py::CliTests"]
      },
      {
        id: "fn_open_ws", kind: "component", label: "_open_workspace_file & search_text", tech: "simple_agent/tools.py:39-255",
        x: 290, y: 165, w: 235, h: 94,
        evidence: "verified",
        summary: "Walks rel_parts via dir_fd + O_DIRECTORY|O_NOFOLLOW|O_PATH, verifies S_ISREG via lstat & fstat, opens with O_RDONLY|O_NONBLOCK|O_NOFOLLOW. Prevents symlink swaps & FIFO hangs.",
        files: ["simple_agent/tools.py:39-127", "simple_agent/tools.py:142-255"],
        excerpts: ["tools_fd_open", "tool_read_file"],
        tests: ["tests/test_tools.py (15 tests)"]
      }
    ],
    edges: [
      { from: "cls_agent_tui", to: "cls_transcript_ctrl", label: "self._history.rows.extend(lines) + app.invalidate()", evidence: "verified" },
      { from: "cls_agent_tui", to: "cls_transcript", label: "self.transcript = Transcript(self._emit, self._width)", evidence: "verified" },
      { from: "cls_agent_tui", to: "fn_conv_turn", label: "Wraps await agent.invoke_async(prompt)", evidence: "verified" },
      { from: "cls_transcript", to: "cls_streamcell", label: "push(chunk) -> emit(); tail() -> live pane", evidence: "verified" },
      { from: "cls_transcript_ctrl", to: "cls_transcript", label: "Calls _tail_rows() during create_content()", evidence: "verified" }
    ]
  }
};

window.ATLAS_INVENTORY = [
  {
    id: "feat-agent-loop",
    title: "Core Agent Orchestration Loop (Strands + OpenAIModel)",
    category: "orchestration",
    priority: true,
    evidence: "verified",
    entry: "simple_agent/agent.py:22",
    symbols: ["create_agent", "resolve_base_url", "AgentTui._respond"],
    summary: "Wires Strands Agent with OpenAIModel (timeout=180s, max_retries=0, max_tokens=2048, temperature=0.2, cache_prompt=True, enable_thinking=False), SYSTEM_PROMPT, and DEFAULT_TOOLS. Invoked synchronously in CLI/plain or asynchronously via agent.invoke_async() in AgentTui.",
    walkthrough: "wt-orchestration",
    tests: ["tests/test_settings_and_cli.py::BaseUrlTests", "tests/test_tui.py::AgentTuiTests"]
  },
  {
    id: "feat-cli-dispatch",
    title: "CLI Mode Dispatch (One-Shot / Full-Screen TUI / Plain REPL)",
    category: "orchestration",
    priority: false,
    evidence: "verified",
    entry: "simple_agent/cli.py:28",
    symbols: ["run_cli", "main", "interactive_terminal", "run_plain"],
    summary: "Parses optional positional prompt and --pet flag. Routes to one-shot agent(prompt), full-screen AgentTui when stdin/stdout are TTYs and TERM != dumb, or line-oriented run_plain otherwise.",
    walkthrough: "wt-orchestration",
    tests: ["tests/test_settings_and_cli.py::CliTests", "tests/test_tui.py::PlainModePetTests"]
  },
  {
    id: "feat-turn-rollback",
    title: "Transactional Conversation Memory & Rollback",
    category: "memory",
    priority: true,
    evidence: "verified",
    entry: "simple_agent/tui/session.py:10",
    symbols: ["conversation_turn", "AgentTui.interrupt", "AgentTui._respond"],
    summary: "Snapshots agent.messages with messages.copy() before each turn. Any BaseException (Esc -> CancelledError, Ctrl-C -> KeyboardInterrupt, network/HTTP error) restores messages[:] = history so orphaned toolUse blocks never poison future turns.",
    walkthrough: "wt-memory",
    tests: ["tests/test_tui.py::AgentTuiTests::test_escape_stops_stream_and_restores_history", "tests/test_settings_and_cli.py::CliTests::test_one_shot_cli_formats_errors_and_interrupts_without_traceback"]
  },
  {
    id: "feat-clear-cmd",
    title: "Conversation Reset (/clear)",
    category: "memory",
    priority: true,
    evidence: "verified",
    entry: "simple_agent/tui/app.py:823",
    symbols: ["AgentTui.submit", "AgentTui._set_agent", "run_plain"],
    summary: "Replaces self.agent with a fresh agent_factory() instance, reapplies persisted settings, reattaches callback_handler, and deletes transcript rows after _header_len while preserving the header box.",
    walkthrough: "wt-memory",
    tests: ["tests/test_tui.py::AgentTuiTests::test_clear_removes_transcript_and_starts_new_conversation"]
  },
  {
    id: "feat-read-file",
    title: "Sandboxed File Reader Tool (read_file)",
    category: "tools",
    priority: true,
    evidence: "verified",
    entry: "simple_agent/tools.py:84",
    symbols: ["read_file", "_open_workspace_file", "_open_regular_file", "_is_sensitive_path"],
    summary: "Reads UTF-8 files up to 4 KiB whole or 1 MiB with inclusive start_line/end_line (output <= 4 KiB). Uses Path.resolve() confinement plus dir_fd O_DIRECTORY|O_NOFOLLOW|O_PATH traversal and O_NONBLOCK fstat S_ISREG checks.",
    walkthrough: "wt-tools",
    tests: ["tests/test_tools.py::ToolTests", "tests/test_tools.py::WorkspaceSearchTests"]
  },
  {
    id: "feat-search-text",
    title: "Bounded Literal Workspace Search Tool (search_text)",
    category: "tools",
    priority: true,
    evidence: "verified",
    entry: "simple_agent/tools.py:142",
    symbols: ["search_text", "_snippet", "DEFAULT_TOOLS"],
    summary: "Deterministic sorted dir_fd DFS for case-sensitive single-line literals. Enforces 10,000 entries, depth 32, 32 MiB read budget, 1 MiB/file cap, 20 matches, 4 KiB output cap, binary/NUL skip, and JSON-quoted unsafe filenames.",
    walkthrough: "wt-tools",
    tests: ["tests/test_tools.py::WorkspaceSearchTests (10 tests)"]
  },
  {
    id: "feat-current-time",
    title: "Timezone Clock Tool (current_time)",
    category: "tools",
    priority: false,
    evidence: "verified",
    entry: "simple_agent/tools.py:74",
    symbols: ["current_time"],
    summary: "Returns ISO-8601 timestamp via datetime.now(ZoneInfo(timezone)).isoformat(); defaults to UTC and raises ZoneInfoNotFoundError on invalid IANA zones.",
    walkthrough: "wt-tools",
    tests: ["tests/test_tools.py::ToolTests::test_current_time_returns_iso_timestamp_and_rejects_bad_timezone"]
  },
  {
    id: "feat-settings-persistence",
    title: "Atomic XDG Settings Persistence",
    category: "persistence",
    priority: true,
    evidence: "verified",
    entry: "simple_agent/settings.py:12",
    symbols: ["settings_path", "load_settings", "save_settings", "apply_agent_settings", "normalize_agent_name"],
    summary: "Stores JSON under $XDG_CONFIG_HOME/simple-agent/settings.json (default ~/.config/simple-agent/settings.json). Merges keys and writes atomically via tempfile.mkstemp + os.replace; tolerates missing or corrupt JSON.",
    walkthrough: "wt-persistence",
    tests: ["tests/test_settings_and_cli.py::SettingsTests", "tests/test_tui.py::PetTests"]
  },
  {
    id: "feat-settings-editor",
    title: "In-TUI Agent Settings Editor (/settings)",
    category: "persistence",
    priority: true,
    evidence: "verified",
    entry: "simple_agent/tui/app.py:300",
    symbols: ["AgentTui._open_settings", "AgentTui._save_agent_settings"],
    summary: "Modal editor for agent_name and multiline system_prompt (Tab switches field, Ctrl-S saves, Esc cancels). Empty system_prompt sets agent.system_prompt = None. Keeps current conversation alive.",
    walkthrough: "wt-persistence",
    tests: ["tests/test_tui.py::AgentTuiTests::test_settings_editor_updates_the_next_turn_and_persists_after_clear"]
  },
  {
    id: "feat-pet-persistence",
    title: "Companion Pet Picker & Half-Block Sprite Renderer (/pet)",
    category: "persistence",
    priority: false,
    evidence: "verified",
    entry: "simple_agent/tui/pets.py:521",
    symbols: ["pet_rows", "load_pet", "save_pet", "normalize_pet", "AgentTui._open_pet_picker"],
    summary: "15 pixel-art pets packed 2 vertical pixels per terminal row using ▀/▄/█ with truecolor (24-bit) or 6x6x6 256-color fallback. Persisted in settings.json; drops automatically when terminal width < box + pet.",
    walkthrough: "wt-persistence",
    tests: ["tests/test_tui.py::PetTests", "tests/test_tui.py::AgentTuiTests::test_pet_command_and_picker_update_header_and_persist_across_sessions"]
  },
  {
    id: "feat-streamcell-markdown",
    title: "Streaming Markdown & Split-ANSI Sanitizer",
    category: "tui",
    priority: false,
    evidence: "verified",
    entry: "simple_agent/tui/rendering.py:313",
    symbols: ["StreamCell", "sanitize_text", "parse_inline", "render_markdown_line", "render_table", "bold_markdown_style"],
    summary: "Incrementally commits completed Markdown lines and monotonic word-wrapped rows while previewing uncommitted text/tables in side-effect-free tail(). Buffers incomplete ANSI/OSC escapes across chunks (<=256B) and renders bold text in theme-aware red.",
    walkthrough: "wt-tui-markdown",
    tests: ["tests/test_tui.py::TranscriptTests (9 tests)"]
  },
  {
    id: "feat-codex-scroll",
    title: "Codex-Style Sticky-Follow Scrolling & Ctrl-T Pager",
    category: "tui",
    priority: false,
    evidence: "verified",
    entry: "simple_agent/tui/app.py:98",
    symbols: ["TranscriptControl", "_WheelFallbackWindow", "AgentTui._scroll_wheel", "AgentTui._open_pager"],
    summary: "Separates committed rows from live tail(). first_line=None tracks bottom live; scrolling up pins first_line so streaming never jumps the viewport. Supports fractional mouse_scroll_speed, PgUp/PgDn, Ctrl-Home/End, and Ctrl-T vim-style overlay.",
    walkthrough: "wt-tui-markdown",
    tests: ["tests/test_tui.py::AgentTuiTests::test_fullscreen_mouse_wheel_sticky_follow_and_jump_shortcuts", "tests/test_tui.py::AgentTuiTests::test_ctrl_t_transcript_overlay_supports_vim_keys_and_preserves_running_turn"]
  },
  {
    id: "feat-slash-commands",
    title: "Slash Command Parser & Completion",
    category: "tui",
    priority: false,
    evidence: "verified",
    entry: "simple_agent/tui/commands.py:47",
    symbols: ["COMMANDS", "matching_commands", "parse_slash_command", "command_output"],
    summary: "Handles /clear, /exit, /pet [name], /settings, /tools, /status. Resolves unambiguous prefixes, validates extra args, and rejects unknown commands locally without calling the model.",
    walkthrough: "wt-tui-markdown",
    tests: ["tests/test_tui.py::AgentTuiTests::test_tui_rejects_unknown_commands_and_extra_command_args_without_invoking_agent", "tests/test_tui.py::PlainModePetTests"]
  },
  {
    id: "feat-runtime-profiles",
    title: "Local llama.cpp Launcher & Intel UHD 620 Profiles",
    category: "runtime",
    priority: false,
    evidence: "verified",
    entry: "scripts/run_model.py:11",
    symbols: ["model_command", "main"],
    summary: "Constructs llama-server flags for default (E4B, 8192 ctx, q8_0 KV, 99 GPU layers), uhd620-cpu (E2B, --device none, strips LLAMA_ARG_DEVICE), and uhd620-vulkan (E2B, 8 GPU layers). Probes Vulkan via --list-devices before os.execve.",
    walkthrough: "wt-runtime",
    tests: ["tests/test_runtime.py::RuntimeTests (5 tests)"]
  }
];
