---
sidebar_position: 7
---

# Profile Commands Reference

This page covers all commands related to [Kunming profiles](../user-guide/profiles.md). For general CLI commands, see [CLI Commands Reference](./cli-commands.md).

## `kunming profile`

```bash
kunming profile <subcommand>
```

Top-level command for managing profiles. Running `kunming profile` without a subcommand shows help.

| Subcommand | Description |
|------------|-------------|
| `list` | List all profiles. |
| `use` | Set the active (default) profile. |
| `create` | Create a new profile. |
| `delete` | Delete a profile. |
| `show` | Show details about a profile. |
| `alias` | Regenerate the shell alias for a profile. |
| `rename` | Rename a profile. |
| `export` | Export a profile to a tar.gz archive. |
| `import` | Import a profile from a tar.gz archive. |

## `kunming profile list`

```bash
kunming profile list
```

Lists all profiles. The currently active profile is marked with `*`.

**Example:**

```bash
$ kunming profile list
  default
* work
  dev
  personal
```

No options.

## `kunming profile use`

```bash
kunming profile use <name>
```

Sets `<name>` as the active profile. All subsequent `kunming` commands (without `-p`) will use this profile.

| Argument | Description |
|----------|-------------|
| `<name>` | Profile name to activate. Use `default` to return to the base profile. |

**Example:**

```bash
kunming profile use work
kunming profile use default
```

## `kunming profile create`

```bash
kunming profile create <name> [options]
```

Creates a new profile.

| Argument / Option | Description |
|-------------------|-------------|
| `<name>` | Name for the new profile. Must be a valid directory name (alphanumeric, hyphens, underscores). |
| `--clone` | Copy `config.yaml`, `.env`, and `SOUL.md` from the current profile. |
| `--clone-all` | Copy everything (config, memories, skills, sessions, state) from the current profile. |
| `--clone-from <profile>` | Clone from a specific profile instead of the current one. Used with `--clone` or `--clone-all`. |

**Examples:**

```bash
# Blank profile — needs full setup
kunming profile create mybot

# Clone config only from current profile
kunming profile create work --clone

# Clone everything from current profile
kunming profile create backup --clone-all

# Clone config from a specific profile
kunming profile create work2 --clone --clone-from work
```

## `kunming profile delete`

```bash
kunming profile delete <name> [options]
```

Deletes a profile and removes its shell alias.

| Argument / Option | Description |
|-------------------|-------------|
| `<name>` | Profile to delete. |
| `--yes`, `-y` | Skip confirmation prompt. |

**Example:**

```bash
kunming profile delete mybot
kunming profile delete mybot --yes
```

:::warning
This permanently deletes the profile's entire directory including all config, memories, sessions, and skills. Cannot delete the currently active profile.
:::

## `kunming profile show`

```bash
kunming profile show <name>
```

Displays details about a profile including its home directory, configured model, gateway status, skills count, and configuration file status.

| Argument | Description |
|----------|-------------|
| `<name>` | Profile to inspect. |

**Example:**

```bash
$ kunming profile show work
Profile: work
Path:    ~/.kunming/profiles/work
Model:   anthropic/claude-sonnet-4 (anthropic)
Gateway: stopped
Skills:  12
.env:    exists
SOUL.md: exists
Alias:   ~/.local/bin/work
```

## `kunming profile alias`

```bash
kunming profile alias <name> [options]
```

Regenerates the shell alias script at `~/.local/bin/<name>`. Useful if the alias was accidentally deleted or if you need to update it after moving your Kunming installation.

| Argument / Option | Description |
|-------------------|-------------|
| `<name>` | Profile to create/update the alias for. |
| `--remove` | Remove the wrapper script instead of creating it. |
| `--name <alias>` | Custom alias name (default: profile name). |

**Example:**

```bash
kunming profile alias work
# Creates/updates ~/.local/bin/work

kunming profile alias work --name mywork
# Creates ~/.local/bin/mywork

kunming profile alias work --remove
# Removes the wrapper script
```

## `kunming profile rename`

```bash
kunming profile rename <old-name> <new-name>
```

Renames a profile. Updates the directory and shell alias.

| Argument | Description |
|----------|-------------|
| `<old-name>` | Current profile name. |
| `<new-name>` | New profile name. |

**Example:**

```bash
kunming profile rename mybot assistant
# ~/.kunming/profiles/mybot → ~/.kunming/profiles/assistant
# ~/.local/bin/mybot → ~/.local/bin/assistant
```

## `kunming profile export`

```bash
kunming profile export <name> [options]
```

Exports a profile as a compressed tar.gz archive.

| Argument / Option | Description |
|-------------------|-------------|
| `<name>` | Profile to export. |
| `-o`, `--output <path>` | Output file path (default: `<name>.tar.gz`). |

**Example:**

```bash
kunming profile export work
# Creates work.tar.gz in the current directory

kunming profile export work -o ./work-2026-03-29.tar.gz
```

## `kunming profile import`

```bash
kunming profile import <archive> [options]
```

Imports a profile from a tar.gz archive.

| Argument / Option | Description |
|-------------------|-------------|
| `<archive>` | Path to the tar.gz archive to import. |
| `--name <name>` | Name for the imported profile (default: inferred from archive). |

**Example:**

```bash
kunming profile import ./work-2026-03-29.tar.gz
# Infers profile name from the archive

kunming profile import ./work-2026-03-29.tar.gz --name work-restored
```

## `kunming -p` / `kunming --profile`

```bash
kunming -p <name> <command> [options]
kunming --profile <name> <command> [options]
```

Global flag to run any Kunming command under a specific profile without changing the sticky default. This overrides the active profile for the duration of the command.

| Option | Description |
|--------|-------------|
| `-p <name>`, `--profile <name>` | Profile to use for this command. |

**Examples:**

```bash
kunming -p work chat -q "Check the server status"
kunming --profile dev gateway start
kunming -p personal skills list
kunming -p work config edit
```

## `kunming completion`

```bash
kunming completion <shell>
```

Generates shell completion scripts. Includes completions for profile names and profile subcommands.

| Argument | Description |
|----------|-------------|
| `<shell>` | Shell to generate completions for: `bash` or `zsh`. |

**Examples:**

```bash
# Install completions
kunming completion bash >> ~/.bashrc
kunming completion zsh >> ~/.zshrc

# Reload shell
source ~/.bashrc
```

After installation, tab completion works for:
- `kunming profile <TAB>` — subcommands (list, use, create, etc.)
- `kunming profile use <TAB>` — profile names
- `kunming -p <TAB>` — profile names

## See also

- [Profiles User Guide](../user-guide/profiles.md)
- [CLI Commands Reference](./cli-commands.md)
- [FAQ — Profiles section](./faq.md#profiles)
