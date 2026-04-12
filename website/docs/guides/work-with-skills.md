---
sidebar_position: 2
title: "Work with Skills"
description: "How to create, manage, and use skills with Kunming Agent"
---

# Work with Skills

Skills are reusable instructions that teach Kunming Agent how to perform specific tasks. They range from simple formatting guidelines to complex multi-step workflows.

---

## What Are Skills?

A skill is a markdown file with structured instructions that the agent can reference when working on relevant tasks. Skills live in `~/.kunming/skills/` and are automatically loaded based on the conversation context.

Skills can include:

- **Step-by-step procedures** — how to perform a specific task
- **Code patterns** — templates and examples for common operations
- **Best practices** — guidelines for quality and consistency
- **Tool usage** — how to use specific CLIs, APIs, or frameworks
- **Domain knowledge** — specialized information for particular fields

---

## Built-in Skills

Kunming Agent ships with a large library of built-in skills covering:

- **Software development** — Python, JavaScript, Rust, Go, and more
- **DevOps** — Docker, Kubernetes, CI/CD, cloud platforms
- **Data science** — Jupyter, pandas, ML frameworks
- **Creative** — ASCII art, diagrams, generative art
- **Productivity** — email, calendar, notes, documents
- **Research** — academic papers, web scraping, data analysis

See the [Skills Catalog](../reference/skills-catalog.md) for the complete list.

---

## Creating Custom Skills

### Quick Start

Create a skill file in `~/.kunming/skills/`:

```bash
mkdir -p ~/.kunming/skills/my-custom-skill
cat > ~/.kunming/skills/my-custom-skill/SKILL.md << 'EOF'
---
name: my-custom-skill
description: Brief description of what this skill does
version: 1.0.0
author: your-name
---

# My Custom Skill

## When to Use

This skill is relevant when: describing the trigger conditions

## Instructions

1. Step one of the procedure
2. Step two of the procedure
3. Step three of the procedure

## Examples

### Example 1: Basic Usage

```bash
# Show a concrete example
command --flag value
```

### Example 2: Advanced Usage

```bash
# Show a more complex example
command --complex --flags --here
```

## Common Patterns

- Pattern one: explanation
- Pattern two: explanation
- Pattern three: explanation

## Troubleshooting

**Problem**: Description of common issue  
**Solution**: How to resolve it
EOF
```

### Skill Structure

A well-structured skill has these sections:

| Section | Purpose |
|---------|---------|
| **When to Use** | Helps the agent recognize when to apply this skill |
| **Instructions** | The core procedure or guidelines |
| **Examples** | Concrete examples showing the skill in action |
| **Common Patterns** | Reusable snippets and templates |
| **Troubleshooting** | Solutions to common problems |

### Frontmatter Fields

The YAML frontmatter at the top of `SKILL.md` controls metadata:

```yaml
---
name: skill-name                    # Unique identifier (required)
description: What this skill does   # Brief description (required)
version: 1.0.0                      # Semantic version
author: Your Name                   # Author attribution
tags: [python, web, api]            # Categories for organization
requires: [other-skill]             # Dependencies on other skills
---
```

---

## Managing Skills

### List Installed Skills

```bash
km skills list
```

### Install Optional Skills

```bash
# Install from the official catalog
km skills install official/blockchain/solana
km skills install official/mlops/flash-attention

# Install from a GitHub repository
km skills install github:username/repo/skill-name

# Install from a local directory
km skills install /path/to/skill/directory
```

### Uninstall Skills

```bash
km skills uninstall skill-name
```

### Update Skills

```bash
# Update all skills to latest versions
km skills update

# Update a specific skill
km skills update skill-name
```

---

## Platform-Specific Skills

Some skills only make sense on certain platforms. Kunming Agent handles this automatically:

### macOS-Only Skills

Skills in `skills/apple/` only load on macOS:

- `apple-notes` — Manage Apple Notes
- `imessage` — Send/receive iMessages
- `findmy` — Track Apple devices

### Linux-Only Skills

Skills that depend on Linux-specific tools only load on Linux.

### Cross-Platform Skills

Most skills work everywhere. The agent automatically adapts to platform differences (e.g., using `curl` on both macOS and Linux).

---

## Skill Best Practices

### Writing Effective Skills

1. **Be specific** — Include exact commands, flags, and parameters
2. **Show examples** — Concrete examples beat abstract descriptions
3. **Handle errors** — Document common failures and solutions
4. **Stay focused** — One skill should do one thing well
5. **Use the right format** — Code blocks for code, lists for steps

### When to Create a Skill

Create a skill when you find yourself:

- Repeating the same instructions to the agent
- Looking up the same documentation repeatedly
- Following a consistent procedure for a type of task
- Working in a specific domain with specialized knowledge

### Skill vs. Memory

| Use | When |
|-----|------|
| **Skill** | Reusable procedures, code patterns, how-to guides |
| **Memory** | Facts about you, your projects, preferences |

Skills are "how to do things." Memories are "things to know."

---

## Advanced: Skill Composition

Skills can reference and build on each other:

```markdown
## Prerequisites

This skill assumes familiarity with:
- [python-basics](../python-basics/) — Basic Python patterns
- [docker](../docker/) — Container fundamentals

## Instructions

1. First, set up the Python environment (see [python-basics](../python-basics/))
2. Then containerize it following [docker](../docker/) patterns
```

The agent automatically loads prerequisite skills when needed.

---

## Troubleshooting

### Skill Not Loading

**Problem**: You created a skill but the agent doesn't seem to use it.

**Solutions**:

1. **Check the file location** — Must be in `~/.kunming/skills/<skill-name>/SKILL.md`
2. **Verify the frontmatter** — Must have valid YAML with `name` and `description`
3. **Check the trigger** — Make sure your prompt matches the "When to Use" section
4. **Reload skills** — Run `/reload` in the CLI to refresh the skill cache

### Skill Conflicts

**Problem**: Two skills have overlapping functionality.

**Solution**: Use the `requires` field in frontmatter to establish precedence, or merge the skills into one comprehensive skill.

### Skill Too Long

**Problem**: Your skill is very long and hits context limits.

**Solution**: Break it into multiple focused skills with clear dependencies. The agent loads skills dynamically based on relevance.

---

## Next Steps

- Browse the [Skills Catalog](../reference/skills-catalog.md) to see what's available
- Check the [Optional Skills Catalog](../reference/optional-skills-catalog.md) for specialized tools
- Read [Tips & Tricks](./tips.md) for advanced usage patterns
