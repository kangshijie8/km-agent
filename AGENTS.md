# Kunming Agent - Development Guide

Instructions for AI coding assistants and developers working on the kunming-agent codebase.

## Development Environment

```bash
source venv/bin/activate  # ALWAYS activate before running Python
```

## Project Structure

```
kunming-agent/
├── run_agent.py          # AIAgent class — core conversation loop
├── model_tools.py        # Tool orchestration, _discover_tools(), handle_function_call()
├── toolsets.py           # Toolset definitions, _KUNMING_CORE_TOOLS list
├── kunming_constants.py  # Shared constants (get_kunming_home, estimate_tokens_cjk_aware, PROVIDER_ALIASES, PLATFORMS)
├── cli.py                # KunmingCLI class — interactive CLI orchestrator
├── kunming_state.py       # SessionDB �?SQLite session store (FTS5 search)
├── agent/                # Agent internals
│   ├── prompt_builder.py     # System prompt assembly
│   ├── context_compressor.py # Auto context compression
│   ├── prompt_caching.py     # Anthropic prompt caching
│   ├── auxiliary_client.py   # Auxiliary LLM client (vision, summarization, LLM-assisted distillation)
│   ├── model_metadata.py     # Model context lengths, token estimation
│   ├── models_dev.py         # models.dev registry integration (provider-aware context)
│   ├── display.py            # KawaiiSpinner, tool preview formatting
│   ├── skill_commands.py     # Skill slash commands (shared CLI/gateway)
│   ├── trajectory.py         # Trajectory saving helpers
│   ├── memory_provider.py    # Abstract MemoryProvider base class (pluggable backends)
│   ├── memory_manager.py     # MemoryManager — orchestrates builtin + external providers
│   ├── builtin_memory_provider.py  # BuiltinMemoryProvider — three-layer file-backed memory
│   ├── memory_distillation.py      # Offline memory consolidation (Light→REM→Deep→Decay)
│   └── error_learning.py     # Error learning — correction detection, error log, experience retrieval
├── agent/cognitive/       # Advanced cognitive system (optional, requires numpy)
│   ├── neural/            # SONA neural learning (PPO/DQN/A2C, ReasoningBank)
│   ├── experts/           # Expert agent types (55+ specializations)
│   ├── swarm/             # Multi-agent coordination (QueenCoordinator)
│   └── adapters/          # Delegate adapter for cognitive tools
├── kunming_cli/           # CLI subcommands and setup
�?  ├── main.py           # Entry point �?all `km` subcommands
�?  ├── config.py         # DEFAULT_CONFIG, OPTIONAL_ENV_VARS, migration
�?  ├── commands.py       # Slash command definitions + SlashCommandCompleter
�?  ├── callbacks.py      # Terminal callbacks (clarify, sudo, approval)
�?  ├── setup.py          # Interactive setup wizard
�?  ├── skin_engine.py    # Skin/theme engine �?CLI visual customization
�?  ├── skills_config.py  # `km skills` �?enable/disable skills per platform
�?  ├── tools_config.py   # `km tools` �?enable/disable tools per platform
�?  ├── skills_hub.py     # `/skills` slash command (search, browse, install)
�?  ├── models.py         # Model catalog, provider model lists
�?  ├── model_switch.py   # Shared /model switch pipeline (CLI + gateway)
�?  └── auth.py           # Provider credential resolution
├── tools/                # Tool implementations (one file per tool)
�?  ├── registry.py       # Central tool registry (schemas, handlers, dispatch)
�?  ├── approval.py       # Dangerous command detection
�?  ├── terminal_tool.py  # Terminal orchestration
�?  ├── process_registry.py # Background process management
�?  ├── file_tools.py     # File read/write/search/patch
�?  ├── web_tools.py      # Web search/extract (Parallel + Firecrawl)
�?  ├── browser_tool.py   # Browserbase browser automation
�?  ├── code_execution_tool.py # execute_code sandbox
�?  ├── delegate_tool.py  # Subagent delegation
�?  ├── mcp_tool.py       # MCP client (~1050 lines)
�?  └── environments/     # Terminal backends (local, docker, ssh, modal, daytona, singularity)
├── gateway/              # Messaging platform gateway
�?  ├── run.py            # Main loop, slash commands, message dispatch
�?  ├── session.py        # SessionStore �?conversation persistence
�?  └── platforms/        # Adapters: telegram, discord, slack, whatsapp, homeassistant, signal
├── acp_adapter/          # ACP server (VS Code / Zed / JetBrains integration)
├── cron/                 # Scheduler (jobs.py, scheduler.py)
├── environments/         # RL training environments (Atropos)
├── tests/                # Pytest suite (~3000 tests)
└── batch_runner.py       # Parallel batch processing
```

**User config:** `~/.kunming/config.yaml` (settings), `~/.kunming/.env` (API keys)

## File Dependency Chain

```
tools/registry.py  (no deps �?imported by all tool files)
       �?tools/*.py  (each calls registry.register() at import time)
       �?model_tools.py  (imports tools/registry + triggers tool discovery)
       �?run_agent.py, cli.py, batch_runner.py, environments/
```

***

## AIAgent Class (run\_agent.py)

```python
class AIAgent:
    def __init__(self,
        model: str = "anthropic/claude-opus-4.6",
        max_iterations: int = 90,
        enabled_toolsets: list = None,
        disabled_toolsets: list = None,
        quiet_mode: bool = False,
        save_trajectories: bool = False,
        platform: str = None,           # "cli", "telegram", etc.
        session_id: str = None,
        skip_context_files: bool = False,
        skip_memory: bool = False,
        # ... plus provider, api_mode, callbacks, routing params
    ): ...

    def chat(self, message: str) -> str:
        """Simple interface �?returns final response string."""

    def run_conversation(self, user_message: str, system_message: str = None,
                         conversation_history: list = None, task_id: str = None) -> dict:
        """Full interface �?returns dict with final_response + messages."""
```

### Agent Loop

The core loop is inside `run_conversation()` �?entirely synchronous:

```python
while api_call_count < self.max_iterations and self.iteration_budget.remaining > 0:
    response = client.chat.completions.create(model=model, messages=messages, tools=tool_schemas)
    if response.tool_calls:
        for tool_call in response.tool_calls:
            result = handle_function_call(tool_call.name, tool_call.args, task_id)
            messages.append(tool_result_message(result))
        api_call_count += 1
    else:
        return response.content
```

Messages follow OpenAI format: `{"role": "system/user/assistant/tool", ...}`. Reasoning content is stored in `assistant_msg["reasoning"]`.

***

## CLI Architecture (cli.py)

- **Rich** for banner/panels, **prompt\_toolkit** for input with autocomplete
- **KawaiiSpinner** (`agent/display.py`) �?animated faces during API calls, `┊` activity feed for tool results
- `load_cli_config()` in cli.py merges hardcoded defaults + user config YAML
- **Skin engine** (`kunming_cli/skin_engine.py`) �?data-driven CLI theming; initialized from `display.skin` config key at startup; skins customize banner colors, spinner faces/verbs/wings, tool prefix, response box, branding text
- `process_command()` is a method on `KunmingCLI` �?dispatches on canonical command name resolved via `resolve_command()` from the central registry
- Skill slash commands: `agent/skill_commands.py` scans `~/.kunming/skills/`, injects as **user message** (not system prompt) to preserve prompt caching

### Slash Command Registry (`kunming_cli/commands.py`)

All slash commands are defined in a central `COMMAND_REGISTRY` list of `CommandDef` objects. Every downstream consumer derives from this registry automatically:

- **CLI** �?`process_command()` resolves aliases via `resolve_command()`, dispatches on canonical name
- **Gateway** �?`GATEWAY_KNOWN_COMMANDS` frozenset for hook emission, `resolve_command()` for dispatch
- **Gateway help** �?`gateway_help_lines()` generates `/help` output
- **Telegram** �?`telegram_bot_commands()` generates the BotCommand menu
- **Slack** �?`slack_subcommand_map()` generates `/kunming` subcommand routing
- **Autocomplete** �?`COMMANDS` flat dict feeds `SlashCommandCompleter`
- **CLI help** �?`COMMANDS_BY_CATEGORY` dict feeds `show_help()`

### Adding a Slash Command

1. Add a `CommandDef` entry to `COMMAND_REGISTRY` in `kunming_cli/commands.py`:

```python
CommandDef("mycommand", "Description of what it does", "Session",
           aliases=("mc",), args_hint="[arg]"),
```

1. Add handler in `KunmingCLI.process_command()` in `cli.py`:

```python
elif canonical == "mycommand":
    self._handle_mycommand(cmd_original)
```

1. If the command is available in the gateway, add a handler in `gateway/run.py`:

```python
if canonical == "mycommand":
    return await self._handle_mycommand(event)
```

1. For persistent settings, use `save_config_value()` in `cli.py`

**CommandDef fields:**

- `name` �?canonical name without slash (e.g. `"background"`)
- `description` �?human-readable description
- `category` �?one of `"Session"`, `"Configuration"`, `"Tools & Skills"`, `"Info"`, `"Exit"`
- `aliases` �?tuple of alternative names (e.g. `("bg",)`)
- `args_hint` �?argument placeholder shown in help (e.g. `"<prompt>"`, `"[name]"`)
- `cli_only` �?only available in the interactive CLI
- `gateway_only` �?only available in messaging platforms
- `gateway_config_gate` �?config dotpath (e.g. `"display.tool_progress_command"`); when set on a `cli_only` command, the command becomes available in the gateway if the config value is truthy. `GATEWAY_KNOWN_COMMANDS` always includes config-gated commands so the gateway can dispatch them; help/menus only show them when the gate is open.

**Adding an alias** requires only adding it to the `aliases` tuple on the existing `CommandDef`. No other file changes needed �?dispatch, help text, Telegram menu, Slack mapping, and autocomplete all update automatically.

***

## Adding New Tools

Requires changes in **3 files**:

**1. Create** **`tools/your_tool.py`:**

```python
import json, os
from tools.registry import registry

def check_requirements() -> bool:
    return bool(os.getenv("EXAMPLE_API_KEY"))

def example_tool(param: str, task_id: str = None) -> str:
    return json.dumps({"success": True, "data": "..."})

registry.register(
    name="example_tool",
    toolset="example",
    schema={"name": "example_tool", "description": "...", "parameters": {...}},
    handler=lambda args, **kw: example_tool(param=args.get("param", ""), task_id=kw.get("task_id")),
    check_fn=check_requirements,
    requires_env=["EXAMPLE_API_KEY"],
)
```

**2. Add import** in `model_tools.py` `_discover_tools()` list.

**3. Add to** **`toolsets.py`** �?either `_KUNMING_CORE_TOOLS` (all platforms) or a new toolset.

The registry handles schema collection, dispatch, availability checking, and error wrapping. All handlers MUST return a JSON string.

**Path references in tool schemas**: If the schema description mentions file paths (e.g. default output directories), use `display_kunming_home()` to make them profile-aware. The schema is generated at import time, which is after `_apply_profile_override()` sets `KUNMING_HOME`.

**State files**: If a tool stores persistent state (caches, logs, checkpoints), use `get_kunming_home()` for the base directory �?never `Path.home() / ".kunming"`. This ensures each profile gets its own state.

**Agent-level tools** (todo, memory): intercepted by `run_agent.py` before `handle_function_call()`. See `todo_tool.py` for the pattern.

***

## Memory & Learning System

kunming-agent has a built-in three-layer memory architecture with hybrid search,
Ebbinghaus forgetting, offline distillation, and error learning — all **zero external
dependencies** (no vector DB, no embedding API, no MCP tools required).

### Three-Layer Memory Architecture

Inspired by biomimetic memory research (Hindsight, MemOS), memories are organized
into three semantic layers plus a user profile:

| Layer | File | Purpose | Char Limit |
|-------|------|---------|------------|
| **Facts** | `FACTS.md` | Stable knowledge: environment, tools, project conventions | 3000 |
| **Experiences** | `EXPERIENCES.md` | Episodic records: problem-solving, operation outcomes | 4000 |
| **Models** | `MODELS.md` | Abstracted patterns: learned rules, decision strategies | 2000 |
| **User** | `USER.md` | User profile: name, preferences, communication style | 1375 |

**Backward compatibility**: The old `MEMORY.md` is auto-migrated to `FACTS.md` on
first load. The `memory` target in tool calls is an alias for `facts`.

**Frozen snapshot pattern**: Memory is loaded into the system prompt once at session
start. Mid-session writes update files on disk immediately (durable) but do NOT
change the system prompt — this preserves the Anthropic prefix cache for the entire
session. The snapshot refreshes on the next session start.

### Memory Tool (`tools/memory_tool.py`)

Single `memory` tool with four actions:

- **add**: Create a new entry in the specified layer
- **replace**: Update an existing entry (identified by `old_text` substring match)
- **remove**: Delete an entry (identified by `old_text` substring match)
- **recall**: Hybrid search across all layers (FTS keyword + simhash vector)

```python
# Tool call examples:
memory(action="add", target="facts", content="Project uses FastAPI for backend")
memory(action="add", target="experiences", content="Deploy failed — missing .env file")
memory(action="add", target="models", content="Always check .env exists before deploying")
memory(action="recall", target="facts", query="deploy environment")
```

### Hybrid Search (Zero-Dependency)

The `recall` action uses a built-in hybrid scoring system — no external vector DB
or embedding API needed:

- **FTS keyword matching** (35% weight): word overlap, coverage, exact substring bonus.
  Pure Python implementation (not SQLite FTS5), with CJK tokenization support.
- **SimHash vector similarity** (65% weight): hash-based fingerprint comparison using
  `hashlib.md5` — similar texts produce similar fingerprints. 64-bit signatures with
  Hamming distance for O(1) similarity lookup.

Scoring: `hybrid = 0.35 * fts_score + 0.65 * vector_score`. Returns top-8 results
across all layers, ranked by relevance.

### Ebbinghaus Forgetting Curve

Every memory entry has metadata tracked automatically:

```python
{
    "created_at": timestamp,
    "last_accessed": timestamp,
    "access_count": int,
    "importance": float,  # 0.0-1.0, default 0.5
}
```

Retention decays exponentially: `retention = exp(-0.693 * age_days / (half_life * access_boost * importance_factor))`

- **Half-life**: 14 days (configurable via `_EBINGHAUS_HALF_LIFE_DAYS`)
- **Access boost**: `1 + log(1 + access_count) * 0.3` — each recall refreshes retention
- **Importance factor**: `0.5 + importance` — high-importance memories decay slower
- **Protection**: entries containing "preference", "always", "never", "must" are never decayed
- **Threshold**: entries below 15% retention are pruned during distillation

### Memory Distillation (`agent/memory_distillation.py`)

Offline consolidation runs on a cron schedule (default: 3 AM daily). Four phases:

1. **Light phase**: Ingest recent session transcripts as signals
2. **REM phase**: Extract recurring themes + **LLM-assisted pattern extraction**
   (calls `auxiliary_client.call_llm()` to identify deeper rules from candidates)
3. **Deep phase**: Score candidates with 6-dimensional formula, promote top entries
   to `EXPERIENCES.md`
4. **Decay phase**: Run Ebbinghaus forgetting curve to prune stale memories

**LLM-assisted REM**: When `llm_assisted_rem` is enabled (default: True), the REM
phase calls a lightweight LLM to extract 1-3 reusable rules from candidates and
writes them to `MODELS.md`. Falls back to heuristic-only if LLM is unavailable.

**Default config** (enabled by default):

```python
{
    "enabled": True,
    "schedule": "0 3 * * *",
    "min_score": 0.65,
    "max_promotions_per_run": 8,
    "llm_assisted_rem": True,
    "decay_on_distill": True,
}
```

### Error Learning (`agent/error_learning.py`)

Detects user corrections, logs errors with context, and retrieves relevant past
errors to avoid repeating mistakes.

**Correction detection**: Matches user messages against 5 patterns:
- Explicit rejection ("no", "wrong", "错了", "不对")
- Redirect ("instead", "actually", "应该是")
- Reference to previous ("I said", "我之前说过")
- Fix request ("fix", "修改", "改正")
- Correct approach ("the right way is", "正确做法是")

**Error log**: Persisted to `~/.kunming/memories/error_log.json` with deduplication
by content hash. Tracks occurrence count, first/last seen dates, and promotion status.

**Auto-promotion**: Errors occurring ≥3 times are automatically promoted to `MODELS.md`
as rules (e.g., "AVOID: X → INSTEAD: Y").

**Session integration**: At session start, relevant past errors are injected into the
system prompt as `[PAST ERRORS TO AVOID:]` warnings. During conversation, user
corrections are detected and logged in real-time.

### Memory Provider Architecture

The memory system uses a provider pattern for extensibility:

```
MemoryProvider (abstract base class)
├── BuiltinMemoryProvider  — always active, three-layer file-backed memory
└── External providers     — optional, one at a time alongside builtin
```

`MemoryManager` orchestrates providers: `builtin_memory_provider.py` wraps the
`MemoryStore` and exposes it through the `MemoryProvider` interface. External
providers (e.g., ruflo, custom backends) can be added via `memory_provider.py`.

### Memory Files Location

All memory files are stored under `~/.kunming/memories/` (or the profile-specific
`KUNMING_HOME/memories/`):

```
~/.kunming/memories/
├── FACTS.md           # Environment knowledge
├── EXPERIENCES.md     # Problem-solving records
├── MODELS.md          # Learned rules and patterns
├── USER.md            # User profile
└── error_log.json     # Error learning log
```

***

## Adding Configuration

### config.yaml options:

1. Add to `DEFAULT_CONFIG` in `kunming_cli/config.py`
2. Bump `_config_version` (currently 5) to trigger migration for existing users

### .env variables:

1. Add to `OPTIONAL_ENV_VARS` in `kunming_cli/config.py` with metadata:

```python
"NEW_API_KEY": {
    "description": "What it's for",
    "prompt": "Display name",
    "url": "https://...",
    "password": True,
    "category": "tool",  # provider, tool, messaging, setting
},
```

### Config loaders (two separate systems):

| Loader              | Used by                | Location                |
| ------------------- | ---------------------- | ----------------------- |
| `load_cli_config()` | CLI mode               | `cli.py`                |
| `load_config()`     | `km tools`, `km setup` | `kunming_cli/config.py` |
| Direct YAML load    | Gateway                | `gateway/run.py`        |

***

## Skin/Theme System

The skin engine (`kunming_cli/skin_engine.py`) provides data-driven CLI visual customization. Skins are **pure data** �?no code changes needed to add a new skin.

### Architecture

```
kunming_cli/skin_engine.py    # SkinConfig dataclass, built-in skins, YAML loader
~/.kunming/skins/*.yaml       # User-installed custom skins (drop-in)
```

- `init_skin_from_config()` �?called at CLI startup, reads `display.skin` from config
- `get_active_skin()` �?returns cached `SkinConfig` for the current skin
- `set_active_skin(name)` �?switches skin at runtime (used by `/skin` command)
- `load_skin(name)` �?loads from user skins first, then built-ins, then falls back to default
- Missing skin values inherit from the `default` skin automatically

### What skins customize

| Element                  | Skin Key                  | Used By                           |
| ------------------------ | ------------------------- | --------------------------------- |
| Banner panel border      | `colors.banner_border`    | `banner.py`                       |
| Banner panel title       | `colors.banner_title`     | `banner.py`                       |
| Banner section headers   | `colors.banner_accent`    | `banner.py`                       |
| Banner dim text          | `colors.banner_dim`       | `banner.py`                       |
| Banner body text         | `colors.banner_text`      | `banner.py`                       |
| Response box border      | `colors.response_border`  | `cli.py`                          |
| Spinner faces (waiting)  | `spinner.waiting_faces`   | `display.py`                      |
| Spinner faces (thinking) | `spinner.thinking_faces`  | `display.py`                      |
| Spinner verbs            | `spinner.thinking_verbs`  | `display.py`                      |
| Spinner wings (optional) | `spinner.wings`           | `display.py`                      |
| Tool output prefix       | `tool_prefix`             | `display.py`                      |
| Per-tool emojis          | `tool_emojis`             | `display.py` �?`get_tool_emoji()` |
| Agent name               | `branding.agent_name`     | `banner.py`, `cli.py`             |
| Welcome message          | `branding.welcome`        | `cli.py`                          |
| Response box label       | `branding.response_label` | `cli.py`                          |
| Prompt symbol            | `branding.prompt_symbol`  | `cli.py`                          |

### Built-in skins

- `default` �?Classic km gold/kawaii (the current look)
- `ares` �?Crimson/bronze war-god theme with custom spinner wings
- `mono` �?Clean grayscale monochrome
- `slate` �?Cool blue developer-focused theme

### Adding a built-in skin

Add to `_BUILTIN_SKINS` dict in `kunming_cli/skin_engine.py`:

```python
"mytheme": {
    "name": "mytheme",
    "description": "Short description",
    "colors": { ... },
    "spinner": { ... },
    "branding": { ... },
    "tool_prefix": "�?,
},
```

### User skins (YAML)

Users create `~/.kunming/skins/<name>.yaml`:

```yaml
name: cyberpunk
description: Neon-soaked terminal theme

colors:
  banner_border: "#FF00FF"
  banner_title: "#00FFFF"
  banner_accent: "#FF1493"

spinner:
  thinking_verbs: ["jacking in", "decrypting", "uploading"]
  wings:
    - ["⟨⚡", "⚡⟩"]

branding:
  agent_name: "Cyber Agent"
  response_label: " �?Cyber "

tool_prefix: "�?
```

Activate with `/skin cyberpunk` or `display.skin: cyberpunk` in config.yaml.

***

## Important Policies

### Prompt Caching Must Not Break

kunming-agent ensures caching remains valid throughout a conversation. **Do NOT implement changes that would:**

- Alter past context mid-conversation
- Change toolsets mid-conversation
- Reload memories or rebuild system prompts mid-conversation

Cache-breaking forces dramatically higher costs. The ONLY time we alter context is during context compression.

### Working Directory Behavior

- **CLI**: Uses current directory (`.` �?`os.getcwd()`)
- **Messaging**: Uses `MESSAGING_CWD` env var (default: home directory)

### Background Process Notifications (Gateway)

When `terminal(background=true, check_interval=...)` is used, the gateway runs a watcher that
pushes status updates to the user's chat. Control verbosity with `display.background_process_notifications`
in config.yaml (or `KUNMING_BACKGROUND_NOTIFICATIONS` env var):

- `all` �?running-output updates + final message (default)
- `result` �?only the final completion message
- `error` �?only the final message when exit code != 0
- `off` �?no watcher messages at all

***

## Profiles: Multi-Instance Support

km supports **profiles** �?multiple fully isolated instances, each with its own
`KUNMING_HOME` directory (config, API keys, memory, sessions, skills, gateway, etc.).

The core mechanism: `_apply_profile_override()` in `kunming_cli/main.py` sets
`KUNMING_HOME` before any module imports. All 119+ references to `get_kunming_home()`
automatically scope to the active profile.

### Rules for profile-safe code

1. **Use** **`get_kunming_home()`** **for all KUNMING\_HOME paths.** Import from `kunming_constants`.
   NEVER hardcode `~/.kunming` or `Path.home() / ".kunming"` in code that reads/writes state.
   ```python
   # GOOD
   from kunming_constants import get_kunming_home
   config_path = get_kunming_home() / "config.yaml"

   # BAD �?breaks profiles
   config_path = Path.home() / ".kunming" / "config.yaml"
   ```
2. **Use** **`display_kunming_home()`** **for user-facing messages.** Import from `kunming_constants`.
   This returns `~/.kunming` for default or `~/.kunming/profiles/<name>` for profiles.
   ```python
   # GOOD
   from kunming_constants import display_kunming_home
   print(f"Config saved to {display_kunming_home()}/config.yaml")

   # BAD �?shows wrong path for profiles
   print("Config saved to ~/.kunming/config.yaml")
   ```
3. **Module-level constants are fine** �?they cache `get_kunming_home()` at import time,
   which is AFTER `_apply_profile_override()` sets the env var. Just use `get_kunming_home()`,
   not `Path.home() / ".kunming"`.
4. **Tests that mock** **`Path.home()`** **must also set** **`KUNMING_HOME`** �?since code now uses
   `get_kunming_home()` (reads env var), not `Path.home() / ".kunming"`:
   ```python
   with patch.object(Path, "home", return_value=tmp_path), \
        patch.dict(os.environ, {"KUNMING_HOME": str(tmp_path / ".kunming")}):
       ...
   ```
5. **Gateway platform adapters should use token locks** �?if the adapter connects with
   a unique credential (bot token, API key), call `acquire_scoped_lock()` from
   `gateway.status` in the `connect()`/`start()` method and `release_scoped_lock()` in
   `disconnect()`/`stop()`. This prevents two profiles from using the same credential.
   See `gateway/platforms/telegram.py` for the canonical pattern.
6. **Profile operations are HOME-anchored, not KUNMING\_HOME-anchored** �?`_get_profiles_root()`
   returns `Path.home() / ".kunming" / "profiles"`, NOT `get_kunming_home() / "profiles"`.
   This is intentional �?it lets `km -p coder profile list` see all profiles regardless
   of which one is active.

## Known Pitfalls

### DO NOT hardcode `~/.kunming` paths

Use `get_kunming_home()` from `kunming_constants` for code paths. Use `display_kunming_home()`
for user-facing print/log messages. Hardcoding `~/.kunming` breaks profiles — each profile
has its own `KUNMING_HOME` directory. This was the source of 5 bugs fixed in PR #3575.

### DO NOT duplicate utility functions across modules

The following utilities have been consolidated into `kunming_constants.py` as single-source-of-truth:
- `estimate_tokens_cjk_aware()` — CJK-aware token estimation (was in 3 files with different algorithms)
- `PROVIDER_ALIASES` — provider name alias mapping (was in auth.py + models.py with inconsistencies)
- `PLATFORMS` — platform definitions dict (was in skills_config.py + tools_config.py with different structures)
- `HYBRID_SEARCH_FTS_WEIGHT` / `HYBRID_SEARCH_VECTOR_WEIGHT` — hybrid search weights

Other consolidated utilities:
- `load_env()` — only in `kunming_cli/config.py` (was also in skills_tool.py without Windows encoding)
- `_deep_merge()` — only in `kunming_cli/config.py` (was also in skin_engine.py without model field handling)
- `simhash_similarity()` — only in `utils.py` (was also as MemoryStore._simhash_similarity)

When adding new utility functions, check `kunming_constants.py` and `utils.py` first. If a function
is used by 2+ modules, it belongs in a shared module, not duplicated locally.

### DO NOT use module-level `get_kunming_home()` calls

Module-level constants like `KUNMING_DIR = get_kunming_home()` are evaluated at import time,
before `_apply_profile_override()` may have set the correct `KUNMING_HOME`. Use lazy evaluation
instead:

```python
# BAD — evaluated at import time, may get wrong path for profiles
KUNMING_DIR = get_kunming_home()

# GOOD — evaluated at call time, always gets correct path
def _get_kunming_dir():
    return get_kunming_home()
```

This pattern was the source of a profile isolation bug in `cron/jobs.py`.

### Cognitive module is optional (requires numpy)

`agent/cognitive/` provides advanced features (SONA neural learning, expert agents, swarm coordination)
but depends on `numpy`. The import in `run_agent.py` uses try/except with `_COGNITIVE_AVAILABLE` flag.
When numpy is missing, `enable_learning` is automatically disabled and the agent runs normally
without cognitive features. Do NOT add hard imports from `agent/cognitive` in core modules.

### DO NOT use `simple_term_menu` for interactive menus

Rendering bugs in tmux/iTerm2 �?ghosting on scroll. Use `curses` (stdlib) instead. See `kunming_cli/tools_config.py` for the pattern.

### DO NOT use `\033[K` (ANSI erase-to-EOL) in spinner/display code

Leaks as literal `?[K` text under `prompt_toolkit`'s `patch_stdout`. Use space-padding: `f"\r{line}{' ' * pad}"`.

### `_last_resolved_tool_names` is a process-global in `model_tools.py`

`_run_single_child()` in `delegate_tool.py` saves and restores this global around subagent execution. If you add new code that reads this global, be aware it may be temporarily stale during child agent runs.

### DO NOT hardcode cross-tool references in schema descriptions

Tool schema descriptions must not mention tools from other toolsets by name (e.g., `browser_navigate` saying "prefer web\_search"). Those tools may be unavailable (missing API keys, disabled toolset), causing the model to hallucinate calls to non-existent tools. If a cross-reference is needed, add it dynamically in `get_tool_definitions()` in `model_tools.py` �?see the `browser_navigate` / `execute_code` post-processing blocks for the pattern.

### Tests must not write to `~/.kunming/`

The `_isolate_kunming_home` autouse fixture in `tests/conftest.py` redirects `KUNMING_HOME` to a temp dir. Never hardcode `~/.kunming/` paths in tests.

**Profile tests**: When testing profile features, also mock `Path.home()` so that
`_get_profiles_root()` and `_get_default_kunming_home()` resolve within the temp dir.
Use the pattern from `tests/kunming_cli/test_profiles.py`:

```python
@pytest.fixture
def profile_env(tmp_path, monkeypatch):
    home = tmp_path / ".kunming"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("KUNMING_HOME", str(home))
    return home
```

***

## Testing

```bash
source venv/bin/activate
python -m pytest tests/ -q          # Full suite (~3000 tests, ~3 min)
python -m pytest tests/test_model_tools.py -q   # Toolset resolution
python -m pytest tests/test_cli_init.py -q       # CLI config loading
python -m pytest tests/gateway/ -q               # Gateway tests
python -m pytest tests/tools/ -q                 # Tool-level tests
```

Always run the full suite before pushing changes.


---

## Complex Task Processing Protocol (User-defined)

The following protocol MUST be applied to all future collaboration sessions on this project. It overrides any generic defaults when there is a conflict.

### 1. Pre-work (Mandatory)

Before starting **any** task, read these two files in the project root **completely**:

- `工作日志.txt` — latest status, active issues, and recent decisions.
- `AGENTS.md` — project architecture, conventions, and historical fixes.

### 2. Task Planning

For non-trivial or complex tasks:

- **Use the subagent parallelization mechanism** (`Agent` tool) to break work into independent investigations or implementations.
- Build a detailed task list with `SetTodoList`.
- Assess dependencies and risks **before** writing code.
- Prefer explicit planning (e.g., `EnterPlanMode`) for multi-file changes or architectural decisions.

### 3. Communication Style

- Be direct and efficient.
- Fix problems immediately, then verify (run tests, inspect output).
- Search the web or explain code when uncertain—**ask for clarification instead of guessing**.
- State all assumptions explicitly before acting.

### 4. Coding Principles

- **Minimal code only**: no over-engineering, no speculative abstractions, and no unrequested configurability.
- **Surgical changes**: touch only the lines necessary to achieve the goal.
- **Match existing style**: formatting, naming, and idioms must blend with the surrounding codebase.
- **Clean up after yourself**: remove unused imports, dead variables, or leftover debug code introduced by the change.
- **Target-driven**: define success criteria as concrete, verifiable goals (e.g., *"write a repro test and make it pass"*).
- **All modifications must be annotated with comments** explaining *why* the change was made, especially for bug fixes or non-obvious logic.

### 5. Verification

- After every code change, run relevant verification (tests, lint, type-check, or manual reproduction).
- Do not declare success until the verification output proves it.
