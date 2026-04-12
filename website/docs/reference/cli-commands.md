---
sidebar_position: 1
title: "CLI Commands Reference"
description: "Authoritative reference for Kunming terminal commands and command families"
---

# CLI Commands Reference

This page covers the **terminal commands** you run from your shell.

For in-chat slash commands, see [Slash Commands Reference](./slash-commands.md).

---

## Global entrypoint

```bash
km [global-options] <command> [subcommand/options]
```

### Global options

| Option | Description |
|--------|-------------|
| `--version`, `-V` | Show version and exit. |
| `--profile <name>`, `-p <name>` | Select which Kunming profile to use for this invocation. Overrides the sticky default set by `km profile use`. |
| `--resume <session>`, `-r <session>` | Resume a previous session by ID or title. |
| `--continue [name]`, `-c [name]` | Resume the most recent session, or the most recent session matching a title. |
| `--worktree`, `-w` | Start in an isolated git worktree for parallel-agent workflows. |
| `--yolo` | Bypass dangerous-command approval prompts. |
| `--pass-session-id` | Include the session ID in the agent's system prompt. |

---

## Top-level commands

| Command | Purpose |
|---------|---------|
| `km chat` | Interactive or one-shot chat with the agent. |
| `km model` | Interactively choose the default provider and model. |
| `km gateway` | Run or manage the messaging gateway service. |
| `km setup` | Interactive setup wizard for all or part of the configuration. |
| `km whatsapp` | Configure and pair the WhatsApp bridge. |
| `km auth` | Manage credentials — add, list, remove, reset, set strategy. Handles OAuth flows for Codex//Anthropic. |
| `km login` / `logout` | **Deprecated** — use `km auth` instead. |
| `km status` | Show agent, auth, and platform status. |
| `km cron` | Inspect and tick the cron scheduler. |
| `km webhook` | Manage dynamic webhook subscriptions for event-driven activation. |
| `km doctor` | Diagnose config and dependency issues. |
| `km config` | Show, edit, migrate, and query configuration files. |
| `km pairing` | Approve or revoke messaging pairing codes. |
| `km skills` | Browse, install, publish, audit, and configure skills. |
| `km honcho` | Manage Honcho cross-session memory integration. |
| `km memory` | Configure external memory provider. |
| `km acp` | Run Kunming as an ACP server for editor integration. |
| `km mcp` | Manage MCP server configurations and run Kunming as an MCP server. |
| `km plugins` | Manage Kunming Agent plugins (install, enable, disable, remove). |
| `km tools` | Configure enabled tools per platform. |
| `km sessions` | Browse, export, prune, rename, and delete sessions. |
| `km insights` | Show token/cost/activity analytics. |
| `km profile` | Manage profiles — multiple isolated Kunming instances. |
| `km completion` | Print shell completion scripts (bash/zsh). |
| `km version` | Show version information. |
| `km update` | Pull latest code and reinstall dependencies. |
| `km uninstall` | Remove Kunming from the system. |

---

## `km chat`

```bash
km chat [options]
```

Common options:

| Option | Description |
|--------|-------------|
| `-q`, `--query "..."` | One-shot, non-interactive prompt. |
| `-m`, `--model <model>` | Override the model for this run. |
| `-t`, `--toolsets <csv>` | Enable a comma-separated set of toolsets. |
| `--provider <provider>` | Force a provider: `auto`, `openrouter`, `nous`, `openai-codex`, `copilot-acp`, `copilot`, `anthropic`, `huggingface`, `zai`, `kimi-coding`, `minimax`, `minimax-cn`, `deepseek`, `ai-gateway`, `opencode-zen`, `opencode-go`, `kilocode`, `alibaba`. |
| `-s`, `--skills <name>` | Preload one or more skills for the session (can be repeated or comma-separated). |
| `-v`, `--verbose` | Verbose output. |
| `-Q`, `--quiet` | Programmatic mode: suppress banner/spinner/tool previews. |
| `--resume <session>` / `--continue [name]` | Resume a session directly from `chat`. |
| `--worktree` | Create an isolated git worktree for this run. |
| `--checkpoints` | Enable filesystem checkpoints before destructive file changes. |
| `--yolo` | Skip approval prompts. |
| `--pass-session-id` | Pass the session ID into the system prompt. |
| `--source <tag>` | Session source tag for filtering (default: `cli`). Use `tool` for third-party integrations that should not appear in user session lists. |
| `--max-turns <N>` | Maximum tool-calling iterations per conversation turn (default: 90, or `agent.max_turns` in config). |

Examples:

```bash
km
km chat -q "Summarize the latest PRs"
km chat --provider openrouter --model anthropic/claude-sonnet-4.6
km chat --toolsets web,terminal,skills
km chat --quiet -q "Return only JSON"
km chat --worktree -q "Review this repo and open a PR"
```

---

## `km model`

Interactive provider + model selector.

```bash
km model
```

Use this when you want to:
- switch default providers
- log into OAuth-backed providers during model selection
- pick from provider-specific model lists
- configure a custom/self-hosted endpoint
- save the new default into config

### `/model` slash command (mid-session)

Switch models without leaving a session:

```
/model                              # Show current model and available options
/model claude-sonnet-4              # Switch model (auto-detects provider)
/model zai:glm-5                    # Switch provider and model
/model custom:qwen-2.5              # Use model on your custom endpoint
/model custom                       # Auto-detect model from custom endpoint
/model custom:local:qwen-2.5        # Use a named custom provider
/model openrouter:anthropic/claude-sonnet-4  # Switch back to cloud
```

Provider and base URL changes are persisted to `config.yaml` automatically. When switching away from a custom endpoint, the stale base URL is cleared to prevent it leaking into other providers.

---

## `km gateway`

```bash
km gateway <subcommand>
```

Subcommands:

| Subcommand | Description |
|------------|-------------|
| `run` | Run the gateway in the foreground. |
| `start` | Start the installed gateway service. |
| `stop` | Stop the service. |
| `restart` | Restart the service. |
| `status` | Show service status. |
| `install` | Install as a user service (`systemd` on Linux, `launchd` on macOS). |
| `uninstall` | Remove the installed service. |
| `setup` | Interactive messaging-platform setup. |

---

## `km setup`

```bash
km setup [model|terminal|gateway|tools|agent] [--non-interactive] [--reset]
```

Use the full wizard or jump into one section:

| Section | Description |
|---------|-------------|
| `model` | Provider and model setup. |
| `terminal` | Terminal backend and sandbox setup. |
| `gateway` | Messaging platform setup. |
| `tools` | Enable/disable tools per platform. |
| `agent` | Agent behavior settings. |

Options:

| Option | Description |
|--------|-------------|
| `--non-interactive` | Use defaults / environment values without prompts. |
| `--reset` | Reset configuration to defaults before setup. |

---

## `km whatsapp`

```bash
km whatsapp
```

Runs the WhatsApp pairing/setup flow, including mode selection and QR-code pairing.

---

## `km login` / `km logout` *(Deprecated)*

:::caution
`km login` has been Nous Portal. Use `km auth` to manage OAuth credentials, `km model` to select a provider, or `km setup