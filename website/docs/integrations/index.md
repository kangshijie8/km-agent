---
sidebar_position: 0
title: "Integrations Overview"
description: "Connect Kunming Agent to external services, platforms, and tools"
---

# Integrations

Kunming Agent integrates with a wide variety of external services, platforms, and tools to extend its capabilities.

---

## LLM Providers

Connect to large language models from various providers:

- **[OpenRouter](providers.md)** — Unified access to 100+ models (recommended)
- **[Anthropic](providers.md)** — Claude models directly
- **[OpenAI](providers.md)** — GPT-4, o1 models
- **[Google](providers.md)** — Gemini models
- **[DeepSeek](providers.md)** — DeepSeek models
- **[Local Models](providers.md)** — Ollama, vLLM, SGLang

Quick setup:

```bash
km model
```

---

## Messaging Platforms

Deploy Kunming Agent as a bot on messaging platforms:

| Platform | Gateway Setup |
|----------|--------------|
| **Telegram** | `km gateway setup` then select Telegram |
| **Discord** | `km gateway setup` then select Discord |
| **Slack** | `km gateway setup` then select Slack |
| **WhatsApp** | `km gateway setup` then select WhatsApp |
| **Signal** | `km gateway setup` then select Signal |
| **Email** | `km gateway setup` then select Email |
| **Home Assistant** | `km gateway setup` then select Home Assistant |

---

## Editor Integration

Use Kunming Agent directly in your code editor:

- **VS Code** — Via ACP (Agent Coding Protocol)
- **Zed** — Via ACP
- **JetBrains** — Via ACP

```bash
pip install -e '.[acp]'
km acp
```

See the [ACP Editor Integration](../user-guide/features/acp.md) guide.

---

## External Tools

### Model Context Protocol (MCP)

Connect to MCP servers for additional tools:

```yaml
# ~/.kunming/config.yaml
mcp_servers:
  github:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-github"]
```

See the [Use MCP with Kunming](./use-mcp-with-kunming.md) guide.

---

## Cloud Services

### AWS

Configure AWS credentials for cloud operations:

```bash
km config set AWS_ACCESS_KEY_ID xxx
km config set AWS_SECRET_ACCESS_KEY xxx
km config set AWS_DEFAULT_REGION us-west-2
```

### Azure

```bash
km config set AZURE_OPENAI_ENDPOINT https://xxx.openai.azure.com
km config set AZURE_OPENAI_KEY xxx
```

---

## Development Tools

### Docker

Run the agent in Docker containers:

```bash
# Run in Docker
docker run -it km/km-model km chat

# Or use the Docker backend for terminal isolation
km config set terminal.backend docker
```

### SSH

Connect to remote servers:

```bash
km config set terminal.backend ssh
km config set terminal.ssh.host user@server.com
```

---

## Productivity Tools

### Google Workspace

```bash
km skills install official/productivity/google-workspace
```

Access Gmail, Calendar, Drive, and more.

### Notion

```bash
km skills install official/productivity/notion
```

### Linear

```bash
km skills install official/productivity/linear
```

### Obsidian

```bash
km skills install official/note-taking/obsidian
```

---

## Security Tools

### 1Password

```bash
km skills install official/security/1password
```

Manage secrets and credentials securely.

---

## Next Steps

- [Set up LLM Providers](providers.md) — Configure your preferred model
- [Messaging Gateway](../user-guide/messaging/index.md) — Deploy on Telegram, Discord, Slack, etc.
- [Skills Catalog](../reference/skills-catalog.md) — Browse available skills
- [MCP Integration](./use-mcp-with-kunming.md) — Connect external tools
