---
sidebar_position: 6
title: "Team Telegram Assistant"
description: "Deploy Kunming Agent as a shared team assistant on Telegram"
---

# Team Telegram Assistant

Deploy Kunming Agent as a shared assistant for your team on Telegram. Multiple team members can interact with the agent in group chats or private messages.

---

## Overview

Kunming Agent's Telegram gateway supports:

- **Group chats** — Multiple team members interacting together
- **Private messages** — One-on-one conversations with the bot
- **Thread-based sessions** — Conversations maintain context within threads
- **Access control** — Allowlist or DM pairing for security
- **Skills** — Full skill library available in Telegram

---

## Quick Setup

### 1. Create a Telegram Bot

Talk to [@BotFather](https://t.me/BotFather) on Telegram:

```
/newbot
# Follow prompts to name your bot
# Save the API token BotFather gives you
```

### 2. Configure Kunming Agent

```bash
# Start the setup wizard
km gateway setup

# Select Telegram
# Enter your bot token when prompted
```

Or edit `~/.kunming/config.yaml` directly:

```yaml
gateway:
  telegram:
    enabled: true
    bot_token: "your-bot-token-here"
    authorized_users: []  # Fill in user IDs after first run
```

### 3. Start the Gateway

```bash
km gateway start
```

Your bot is now live on Telegram.

---

## Access Control

### Finding User IDs

When someone messages your bot, check the logs:

```bash
cat ~/.kunming/logs/gateway.log | grep "user_id"
```

Add authorized users to your config:

```yaml
gateway:
  telegram:
    authorized_users:
      - 123456789  # Your user ID
      - 987654321  # Team member's ID
```

Restart the gateway after updating:

```bash
km gateway restart
```

### Authorization Modes

| Mode | How It Works | Best For |
|------|--------------|----------|
| **Allowlist** | Only listed user IDs can interact | Controlled team access |
| **DM Pairing** | First user to DM the bot claims it | Personal assistant |
| **Open** | Anyone can interact (no restrictions) | Public bots (rare) |

Configure in `~/.kunming/config.yaml`:

```yaml
gateway:
  telegram:
    authorization_mode: "allowlist"  # or "dm_pairing", "open"
```

---

## Group Chat Setup

### Adding to Groups

1. Add your bot to a Telegram group
2. Give it permission to read messages
3. Mention the bot to start interacting:

```
@your_bot_name summarize the latest PR
```

### Group-Specific Behavior

- Sessions are **per-user** in groups by default
- Each user has their own conversation context
- Use threads (Telegram topics) for shared context

### Thread-Based Sessions

In Telegram groups with topics enabled:

1. Create a thread/topic for agent discussions
2. All messages in that thread share context
3. Multiple users can collaborate in one session

---

## Skills in Telegram

All Kunming Agent skills work in Telegram:

```
@your_bot_name create a Python script that fetches weather data
@your_bot_name search for Python best practices
@your_bot_name review the code in https://github.com/user/repo
```

### Managing Skills for Telegram

Telegram has a 100 command limit for bot menus. Disable unused skills:

```bash
km skills config
# Select "telegram"
# Disable skills you don't need
```

This updates `config.yaml`:

```yaml
skills:
  platform_disabled:
    telegram:
      - skill-you-dont-need
      - another-unused-skill
```

---

## Slash Commands

Kunming Agent supports these slash commands in Telegram:

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/model` | Switch LLM model |
| `/usage` | Check token usage |
| `/compress` | Compress conversation history |
| `/clear` | Clear current conversation |
| `/memory` | Manage memories |
| `/todo` | Show todo list |

Type `/help` in Telegram to see the full list.

---

## Customizing Responses

### Hide Tool Activity

For cleaner output in group chats:

```yaml
display:
  tool_progress: "off"  # Only show final responses
```

Options:
- `off` — Final response only
- `new` — Brief tool call notifications
- `all` — Show all tool activity
- `verbose` — Full detail

### Response Formatting

Kunming Agent automatically formats responses for Telegram:

- Code blocks with syntax highlighting
- Bold and italic text
- Lists and tables
- Links

---

## Deployment Options

### Local Machine

Run the gateway on your local machine:

```bash
km gateway start
```

Good for: Personal use, small teams, testing

### VPS/Server

Deploy to a cloud server for 24/7 availability:

```bash
# On your server
curl -fsSL https://raw.githubusercontent.com/kunming/km-agent/main/scripts/install.sh | bash
km setup
km gateway setup  # Configure Telegram

# Run persistently
km gateway start --daemon
```

Good for: Production teams, always-on assistance

### Docker

Run in a container:

```bash
docker run -d \
  -v ~/.kunming:/root/.kunming \
  -e TELEGRAM_BOT_TOKEN=your-token \
  km/km-model \
  km gateway start
```

---

## Advanced Configuration

### Webhook Mode (Production)

For better performance with many users, use webhooks instead of polling:

```yaml
gateway:
  telegram:
    webhook_url: "https://your-domain.com/webhook"
    webhook_port: 8080
```

Requires:
- Public domain with HTTPS
- Port forwarding or reverse proxy

### Multiple Bots

Run multiple Telegram bots (different profiles):

```bash
# Create a new profile
km profile create work

# Configure bot in this profile
km -p work gateway setup
km -p work gateway start
```

Each profile has isolated config, memory, and sessions.

---

## Troubleshooting

### Bot Not Responding

```bash
# Check if gateway is running
km gateway status

# View logs
cat ~/.kunming/logs/gateway.log | tail -50

# Restart
km gateway restart
```

### User Not Authorized

If users see "not authorized" errors:

1. Check `authorized_users` in config.yaml
2. Get their user ID from logs
3. Add them and restart

### Commands Not Showing

If the bot command menu is empty:

1. Check you haven't exceeded 100 commands
2. Disable unused skills: `km skills config`
3. Restart the gateway

### Rate Limiting

Telegram has rate limits. If hitting limits:

- Reduce message frequency
- Use longer, more detailed prompts
- Consider webhook mode for high-traffic bots

---

## Best Practices

### Security

- Use allowlist mode for team bots
- Don't share bot tokens
- Regularly review authorized users
- Use DM pairing for personal bots

### Performance

- Disable unused skills
- Use `tool_progress: off` for cleaner output
- Compress long conversations regularly
- Consider webhook mode for busy bots

### User Experience

- Pin important messages in group chats
- Use threads for different topics
- Set clear expectations about response times
- Share common commands with your team

---

## Next Steps

- Learn about [Daily Briefing Bots](./daily-briefing-bot.md) for automated updates
- Set up [Cron Jobs](./automate-with-cron.md) for scheduled tasks
- Explore other [Messaging Platforms](../user-guide/messaging/index.md)
