---
sidebar_position: 7
title: "Daily Briefing Bot"
description: "Create an automated daily briefing bot with Kunming Agent"
---

# Daily Briefing Bot

Build an automated daily briefing bot that aggregates news, weather, calendar events, and custom data sources, then delivers a formatted summary to your preferred messaging platform.

---

## Overview

A daily briefing bot can:

- **Aggregate news** — From RSS feeds, APIs, or web sources
- **Check weather** — For your location or travel destinations
- **Review calendar** — Upcoming meetings and events
- **Track metrics** — Website analytics, server status, sales data
- **Summarize** — Use AI to create readable briefings
- **Deliver** — Via Telegram, Discord, Slack, or email

---

## Quick Start

### 1. Create the Briefing Script

Create a script that generates your daily briefing:

```bash
mkdir -p ~/.kunming/cron
cat > ~/.kunming/cron/daily-briefing.sh << 'EOF'
#!/bin/bash
# Daily Briefing Generator

# Run the briefing generation
km chat -q "Generate a daily briefing with the following sections:
1. Weather forecast for San Francisco
2. Top 3 tech news headlines
3. Today's calendar events from Google Calendar
4. Any urgent emails flagged in Gmail
5. Server status check for my VPS

Format as a clean markdown report."
EOF

chmod +x ~/.kunming/cron/daily-briefing.sh
```

### 2. Schedule with Cron

Add to your crontab:

```bash
km cron edit
```

Add this line for 8 AM daily:

```
0 8 * * * /home/user/.kunming/cron/daily-briefing.sh >> /home/user/.kunming/logs/briefing.log 2>&1
```

### 3. Add Telegram Delivery

Modify the script to send to Telegram:

```bash
cat > ~/.kunming/cron/daily-briefing.sh << 'EOF'
#!/bin/bash
# Daily Briefing Generator with Telegram Delivery

BRIEFING=$(km chat -q "Generate a daily briefing...")

# Send via Telegram bot (requires TELEGRAM_BOT_TOKEN and CHAT_ID)
curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
  -d "chat_id=$CHAT_ID" \
  -d "text=$BRIEFING" \
  -d "parse_mode=Markdown"
EOF
```

---

## Advanced Briefing Components

### Weather Integration

```bash
# Using Open-Meteo (free, no API key)
km chat -q "Get the weather forecast for San Francisco for today using Open-Meteo API"
```

### News Aggregation

```bash
# RSS feed aggregation
km chat -q "Fetch the latest 5 articles from these RSS feeds:
- https://news.ycombinator.com/rss
- https://techcrunch.com/feed/
Summarize the top stories."
```

### Calendar Integration

Use the Google Workspace skill:

```bash
km skills install official/productivity/google-workspace
km chat -q "List today's events from my Google Calendar"
```

### GitHub Activity

```bash
# Check PRs and issues
km chat -q "List open pull requests and high-priority issues from my GitHub repos"
```

### Server Monitoring

```bash
# Check system health
km chat -q "Check CPU, memory, and disk usage on my VPS. Alert if anything is over 80%."
```

---

## Delivery Methods

### Telegram

```bash
# Via gateway (if already running)
km chat -q "Send this briefing to Telegram"

# Direct API call
curl -X POST "https://api.telegram.org/bot<TOKEN>/sendMessage" \
  -d "chat_id=<CHAT_ID>" \
  -d "text=<BRIEFING>"
```

### Discord

```bash
# Via webhook
curl -X POST "$DISCORD_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d "{\"content\": \"$BRIEFING\"}"
```

### Slack

```bash
# Via webhook
curl -X POST "$SLACK_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d "{\"text\": \"$BRIEFING\"}"
```

### Email

Use the Himalaya skill:

```bash
km chat -q "Send an email to me@example.com with subject 'Daily Briefing' and this content: $BRIEFING"
```

---

## Complete Example

Here's a full-featured daily briefing setup:

### The Briefing Generator

```bash
cat > ~/.kunming/cron/generate-briefing.sh << 'EOF'
#!/bin/bash
set -e

LOG_FILE="/home/user/.kunming/logs/briefing.log"
CONFIG_FILE="/home/user/.kunming/briefing-config.yaml"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "Starting daily briefing generation..."

# Generate the briefing using Kunming Agent
BRIEFING=$(km chat -q "
Generate a comprehensive daily briefing with these sections:

## Weather
Get current weather and forecast for San Francisco, CA using Open-Meteo.

## Tech News
Fetch and summarize top 5 stories from Hacker News RSS.

## Calendar
List today's meetings from Google Calendar (use google-workspace skill).

## Tasks
Show overdue and today's tasks from Linear (if configured).

## Metrics
Check website analytics (if configured) and server status.

Format as clean markdown with emojis for each section.
")

# Save to file for debugging
echo "$BRIEFING" > "/home/user/.kunming/last-briefing.md"

# Send to Telegram
if [ -n "$TELEGRAM_BOT_TOKEN" ] && [ -n "$TELEGRAM_CHAT_ID" ]; then
    log "Sending to Telegram..."
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d "chat_id=${TELEGRAM_CHAT_ID}" \
        -d "text=${BRIEFING}" \
        -d "parse_mode=Markdown" \
        -d "disable_web_page_preview=true" >> "$LOG_FILE" 2>&1
    log "Telegram delivery complete"
fi

# Send to Discord
if [ -n "$DISCORD_WEBHOOK_URL" ]; then
    log "Sending to Discord..."
    # Discord has 2000 char limit, may need to split
    curl -s -X POST "$DISCORD_WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -d "{\"content\": \"📅 Daily Briefing for $(date '+%Y-%m-%d')\"}" >> "$LOG_FILE" 2>&1
    log "Discord delivery complete"
fi

log "Daily briefing complete"
EOF

chmod +x ~/.kunming/cron/generate-briefing.sh
```

### Configuration File

```yaml
# ~/.kunming/briefing-config.yaml
briefing:
  weather:
    location: "San Francisco, CA"
    lat: 37.7749
    lon: -122.4194
  
  news:
    feeds:
      - https://news.ycombinator.com/rss
      - https://techcrunch.com/feed/
    max_articles: 5
  
  calendar:
    provider: google
    look_ahead_days: 1
  
  delivery:
    telegram:
      enabled: true
      chat_id: "your-chat-id"
    discord:
      enabled: false
      webhook_url: "your-webhook-url"
    email:
      enabled: false
      to: "you@example.com"
```

### Cron Schedule

```bash
km cron edit
```

Add multiple briefing times:

```
# Morning briefing at 8 AM
0 8 * * * /home/user/.kunming/cron/generate-briefing.sh

# Evening wrap-up at 6 PM
0 18 * * 1-5 /home/user/.kunming/cron/evening-wrapup.sh

# Weekly summary on Monday mornings
0 9 * * 1 /home/user/.kunming/cron/weekly-summary