---
sidebar_position: 10
title: "Tips & Tricks"
description: "Advanced tips and tricks for getting the most out of Kunming Agent"
---

# Tips & Tricks

Advanced techniques to maximize your productivity with Kunming Agent.

---

## Conversation Management

### Compress Long Conversations

When conversations get long (approaching context limits), use compression:

```bash
/compress
```

This summarizes the conversation history while preserving key context, reducing token usage significantly.

### Check Token Usage

Monitor your session's token consumption:

```bash
/usage
```

Shows current tokens used, remaining budget, and compression opportunities.

### Continue Previous Sessions

Resume a previous conversation:

```bash
km chat --continue
```

Or reference a specific session by ID from `~/.kunming/state.db`.

---

## Working with Files

### Quick File Creation

Create files directly from the CLI:

```bash
km chat -q "Create a Python script that fetches weather data from Open-Meteo and saves it to a CSV"
```

The agent will write the file and confirm the path.

### Batch File Operations

Process multiple files at once:

```bash
# Rename all .txt files to .md
km chat -q "Rename all .txt files in the current directory to .md"

# Convert file formats
km chat -q "Convert all .png files in ./images to .webp with 80% quality"
```

### Project-Wide Changes

Make changes across an entire codebase:

```bash
# Refactor all functions to use async/await
km chat -q "Convert all synchronous database calls in src/ to use async/await"

# Update imports after moving files
km chat -q "Fix all import statements after moving utils.py to src/helpers/"
```

---

## Model Selection Strategies

### Different Models for Different Tasks

Not all models excel at the same things. Consider:

| Task Type | Recommended Models |
|-----------|-------------------|
| **Code generation** | Claude, GPT-4, DeepSeek Coder |
| **Analysis & reasoning** | Claude, GPT-4, o1 |
| **Creative writing** | GPT-4, Claude, Gemini |
| **Quick tasks** | Llama 3.1 8B, GPT-4o-mini |
| **Long context** | Claude 3.5 Sonnet, Gemini 1.5 Pro |

Switch models mid-session:

```bash
/model claude-sonnet-4.6
```

### Delegation for Specialized Work

Route subagents to different models automatically:

```yaml
# In ~/.kunming/config.yaml
delegation:
  model: "google/gemini-3-flash-preview"
  provider: "openrouter"
```

Now when you say "delegate this task," subagents use Gemini while your main conversation stays on your primary model.

---

## Tool Optimization

### Reduce Active Toolsets

Fewer tools = faster responses + lower token usage:

```bash
# Only load terminal tools
km chat -t terminal

# Load terminal + file tools
km chat -t terminal,file

# Exclude heavy toolsets
km chat -T browser,mcp
```

### Tool Result Caching

Kunming Agent automatically caches certain tool results (like web searches) within a session. Reference previous results:

```bash
# First request (cached)
km chat -q "Search for Python async best practices"

# Later reference (uses cache)
km chat -q "Based on those async patterns, refactor my code"
```

---

## Gateway & Messaging

### Hide Tool Activity in Chats

For cleaner messaging output:

```yaml
# In ~/.kunming/config.yaml
display:
  tool_progress: "off"   # Only show final responses
```

Options: `off`, `new`, `all`, `verbose`

### Per-Platform Skills

Disable skills you don't need on specific platforms:

```bash
km skills config
# Select platform (telegram, discord, etc.)
# Disable unused skills
```

This helps stay under Telegram's 100 command limit.

### Shared Thread Sessions

For Slack: sessions are keyed by thread, so multiple users in a thread share context naturally.

For Discord: sessions are keyed by channel, so all users in a channel share context.

---

## Automation Patterns

### Cron Jobs

Schedule recurring tasks:

```bash
# Edit cron jobs
km cron edit

# Example: Daily briefing at 8am
0 8 * * * /home/user/.local/bin/km chat -q "Generate daily briefing and send to Telegram"
```

See [Automate with Cron](./automate-with-cron.md) for details.

### Webhook Triggers

Trigger agents from external services:

```bash
# Set up webhook endpoint
km webhook create --name github-events --port 8080

# Configure GitHub to POST to your endpoint
# Agent processes events automatically
```

### Batch Processing

Process many items in parallel:

```bash
# Create a batch file with one task per line
cat > tasks.txt << 'EOF'
Summarize https://example.com/article1
Summarize https://example.com/article2
Summarize https://example.com/article3
EOF

# Run in parallel
km batch --file tasks.txt --workers 5
```

---

## Memory & Context

### SOUL.md — Project Context

Create a `SOUL.md` in your project root for persistent project context:

```markdown
# Project Context

## Tech Stack
- Python 3.12 with FastAPI
- PostgreSQL with SQLAlchemy
- React frontend with TypeScript

## Architecture
- Clean architecture with domain/services/infra layers
- Event-driven with Redis pub/sub

## Conventions
- Use dependency injection for all services
- Write tests for all new endpoints
- Follow PEP 8 style guide
```

Kunming Agent automatically loads this when working in the project directory.

### Memory Management

Add facts to memory:

```bash
/memory "I prefer 2-space indentation for JavaScript"
/memory "My AWS region is us-west-2"
```

These are retrieved automatically when relevant.

### Context Files

Create `.kunming/context.md` for workspace-specific instructions that persist across sessions.

---

## Security Best Practices

### Dangerous Command Approval

Kunming Agent prompts before running destructive commands (`rm -rf`, `DROP TABLE`, etc.). Always review before approving.

### Sensitive Data

Never paste sensitive data (passwords, API keys, tokens) directly into chats. Use:

```bash
# Reference from environment
km chat -q "Use the API key from $SECRET_API_KEY environment variable"

# Or use 1Password integration
km chat -q "Get the database password from 1Password item 'production-db'"
```

### Sandboxed Execution

For untrusted code:

```bash
# Run in Docker sandbox
km chat -q "Execute this Python script in a Docker container"

# Or use the code execution tool with sandbox enabled
```

---

## Performance Optimization

### Local Models

For completely free, offline operation:

```bash
# Set up Ollama
ollama pull qwen3.5:27b

# Configure Kunming Agent
km model
# Select: Custom endpoint
# URL: http://localhost:11434/v1
# Model: qwen3.5:27b
```

### GPU Acceleration

When using local models, ensure GPU is utilized:

```bash
# Check GPU usage
nvidia-smi

# For Ollama, set GPU layers
ollama run qwen3.5:27b --num_gpu 35
```

### Parallel Tool Execution

Kunming Agent automatically parallelizes independent tool calls. Structure your requests to take advantage:

```bash
# Good: Independent operations
km chat -q "Search for Python tutorials AND find the latest Django release notes"

# Good: Sequential dependencies
km chat -q "Find the latest FastAPI version, then update requirements.txt"
```

---

## Troubleshooting

### Debug Mode

Enable verbose logging:

```bash
km chat --verbose
```

Shows full tool calls, API requests, and timing information.

### Reset Configuration

If config gets corrupted:

```bash
# Back up first
cp ~/.kunming/config.yaml ~/.kunming/config.yaml.bak

# Reset to defaults
rm ~/.kunming/config.yaml
km setup
```

### Clear Cache

If experiencing weird behavior:

