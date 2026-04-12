---
sidebar_position: 9
title: "Automate with Cron"
description: "Schedule recurring tasks and automate workflows with Kunming Agent and cron"
---

# Automate with Cron

Schedule recurring tasks, automated reports, and background workflows using Kunming Agent with cron.

---

## Overview

Cron is a time-based job scheduler that runs commands at specified intervals. Combined with Kunming Agent, you can:

- **Generate daily reports** — Morning briefings, analytics summaries
- **Monitor systems** — Health checks, log analysis, alerting
- **Automate workflows** — Data processing, content publishing
- **Send notifications** — Reminders, status updates
- **Run maintenance** — Cleanup tasks, backups, updates

---

## Quick Start

### Edit Cron Jobs

```bash
km cron edit
```

This opens your crontab in the default editor.

### Add a Simple Job

```
# Run every day at 8 AM
0 8 * * * km chat -q "Generate daily briefing and send to Telegram"
```

### List Cron Jobs

```bash
km cron list
```

---

## Cron Syntax

### Format

```
┌───────────── minute (0 - 59)
│ ┌───────────── hour (0 - 23)
│ │ ┌───────────── day of month (1 - 31)
│ │ │ ┌───────────── month (1 - 12)
│ │ │ │ ┌───────────── day of week (0 - 6, Sunday = 0)
│ │ │ │ │
│ │ │ │ │
* * * * * command
```

### Common Patterns

| Schedule | Description |
|----------|-------------|
| `0 8 * * *` | Every day at 8:00 AM |
| `0 */6 * * *` | Every 6 hours |
| `0 9 * * 1` | Every Monday at 9:00 AM |
| `0 0 1 * *` | First day of every month |
| `*/15 * * * *` | Every 15 minutes |
| `0 9-17 * * 1-5` | Every hour 9 AM - 5 PM on weekdays |

### Online Cron Expression Helpers

- [crontab.guru](https://crontab.guru/) — Visual cron expression editor
- [cron-ai](https://cron-ai.vercel.app/) — Natural language to cron

---

## Kunming Agent Cron Jobs

### Basic Pattern

```bash
# Single command
km chat -q "your prompt here"

# With specific model
km chat --model gpt-4 -q "your prompt"

# With output logging
km chat -q "your prompt" >> /var/log/kunming-cron.log 2>&1
```

### Daily Briefing

```
# Every weekday morning
0 8 * * 1-5 /home/user/.local/bin/km chat -q "Generate morning briefing with weather, news, and calendar" >> /home/user/.kunming/logs/briefing.log 2>&1
```

### System Health Check

```
# Every hour
0 * * * * /home/user/.local/bin/km chat -q "Check server CPU, memory, disk usage. Alert if any metric exceeds 80%" >> /home/user/.kunming/logs/health.log 2>&1
```

### GitHub Activity Summary

```
# Every Friday at 5 PM
0 17 * * 5 /home/user/.local/bin/km chat -q "Summarize this week's GitHub activity: PRs merged, issues closed, commits" >> /home/user/.kunming/logs/github.log 2>&1
```

### Content Publishing

```
# Every Tuesday and Thursday at 10 AM
0 10 * * 2,4 /home/user/.local/bin/km chat -q "Generate blog post about latest tech trends and publish to WordPress" >> /home/user/.kunming/logs/content.log 2>&1
```

---

## Advanced Patterns

### Scripts with Multiple Commands

Create a script for complex workflows:

```bash
# ~/.kunming/cron/weekly-report.sh
#!/bin/bash
set -e

DATE=$(date '+%Y-%m-%d')
LOG_FILE="/home/user/.kunming/logs/weekly-report-${DATE}.log"

{
    echo "Starting weekly report generation..."
    
    # Generate report
    km chat -q "Create weekly summary report covering:
    1. Website analytics from Google Analytics
    2. GitHub repository activity
    3. Support ticket trends
    4. Server uptime statistics
    Save to /home/user/reports/weekly-${DATE}.md"
    
    # Email the report
    km chat -q "Email /home/user/reports/weekly-${DATE}.md to team@example.com with subject 'Weekly Report ${DATE}'"
    
    echo "Weekly report complete"
} >> "$LOG_FILE" 2>&1
```

Add to crontab:

```
0 9 * * 1 /home/user/.kunming/cron/weekly-report.sh
```

### Environment Variables

Cron jobs run with minimal environment. Set required variables:

```
# At the top of your crontab
SHELL=/bin/bash
PATH=/home/user/.local/bin:/usr/local/bin:/usr/bin:/bin
KUNMING_HOME=/home/user/.kunming
OPENROUTER_API_KEY=your-key-here

# Then your jobs
0 8 * * * km chat -q "Generate daily briefing"
```

Or use a wrapper script:

```bash
# ~/.kunming/cron/wrapper.sh
#!/bin/bash
source /home/user/.bashrc
source /home/user/.kunming/.env
export PATH="/home/user/.local/bin:$PATH"

# Run the actual command
km chat -q "$1"
```

### Conditional Execution

Only run if certain conditions are met:

```bash
# Only on production server
0 8 * * * [ "$(hostname)" = "prod-server" ] && km chat -q "Production daily check"

# Only if file exists
0 9 * * 1 [ -f /var/run/enable-reports ] && km chat -q "Generate weekly report"

# Skip on holidays (check against a file)
0 8 * * * grep -q "$(date +%m-%d)" /home/user/.kunming/holidays.txt || km chat -q "Daily briefing"
```

---

## Logging and Monitoring

### Basic Logging

Always redirect output to logs:

```
# Good: Captures output and errors
0 8 * * * km chat -q "Daily task" >> /home/user/.kunming/logs/cron.log 2>&1

# Better: Separate log per job
0 8 * * * km chat -q "Daily task" >> /home/user/.kunming/logs/daily-task.log 2>&1

# Best: With timestamps
0 8 * * * km chat -q "Daily task" 2>&1 | ts '[%Y-%m-%d %H:%M:%S]' >> /home/user/.kunming/logs/daily-task.log
```

### Log Rotation

Prevent logs from growing too large:

```bash
# Add to your crontab
0 0 * * 0 logrotate /home/user/.kunming/cron/logrotate.conf
```

Create `/home/user/.kunming/cron/logrotate.conf`:

```
/home/user/.kunming/logs/*.log {
    weekly
    rotate 4
    compress
    missingok
    notifempty
}
```

### Error Alerting

Get notified when jobs fail:

```bash
# ~/.kunming/cron/monitored-job.sh
#!/bin/bash
JOB_NAME="$1"
shift

LOG_FILE="/home/user/.kunming/logs/${JOB_NAME}.log"
ERROR_LOG="/home/user/.kunming/logs/${JOB_NAME}.errors"

# Run the command
if ! km chat -q "$@" >> "$LOG_FILE" 2>&1; then
    echo "[$(date)] Job $JOB_NAME failed" >> "$ERROR_LOG"
    # Send alert via Telegram
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d "chat_id=${TELEGRAM_CHAT_ID}" \
        -d "text=⚠️ Cron job $JOB_NAME failed. Check logs at $ERROR_LOG"
fi
```

---

## Use Cases

### Morning Briefing