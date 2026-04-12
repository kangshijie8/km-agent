---
sidebar_position: 1
title: "LLM Providers"
description: "Configure and use different LLM providers with Kunming Agent"
---

# LLM Providers

Kunming Agent works with any OpenAI-compatible API. This page covers provider setup, model selection, and configuration details.

---

## Supported Providers

| Provider | Models | Setup |
|---------|--------|-------|
| **OpenRouter** | 100+ models | API key only |
| **Nous Portal** |  models | OAuth login |
| **OpenAI** | GPT-4, o1, o3 | API key |
| **Anthropic** | Claude models | API key |
| **Google** | Gemini models | API key |
| **DeepSeek** | DeepSeek models | API key |
| **Local models** | Any Ollama/vLLM model | Custom endpoint |

---

## Quick Setup

### Interactive Selection

```bash
km model
```

This walks you through provider selection and stores the configuration in `~/.kunming/config.yaml`.

### Manual Configuration

Edit `~/.kunming/config.yaml`:

```yaml
model:
  default: anthropic/claude-sonnet-4.6
  provider: openrouter
  base_url: https://openrouter.ai/api/v1
```

Or use environment variables:

```bash
km config set OPENROUTER_API_KEY sk-or-v1-xxx
```

---

## Provider Details

### OpenRouter (Recommended)

OpenRouter provides unified access to 100+ models from various providers.

**Setup:**
1. Get an API key from [openrouter.ai](https://openrouter.ai/)
2. Run `km model` or set the key manually:
   ```bash
   km config set OPENROUTER_API_KEY sk-or-v1-xxx
   ```

**Model naming:** OpenRouter uses `provider/model` format:
- `anthropic/claude-sonnet-4.6`
- `google/gemini-3-flash-preview`
- `openai/gpt-4o`
- `meta-llama/llama-3.1-70b-instruct`

### Anthropic (Direct)

Access Claude models directly without OpenRouter.

**Setup:**
```bash
km config set ANTHROPIC_API_KEY sk-ant-xxx
```

Set model:
```bash
km model
# Select: Anthropic
# Select: claude-sonnet-4.6 (or other)
```

### OpenAI (Direct)

**Setup:**
```bash
km config set OPENAI_API_KEY sk-xxx
```

Models: `gpt-4o`, `gpt-4-turbo`, `o1-preview`, `o1-mini`

### Google

**Setup:**
```bash
km config set GOOGLE_API_KEY xxx
```

Models: `gemini-1.5-pro`, `gemini-1.5-flash`

### DeepSeek

**Setup:**
```bash
km config set DEEPSEEK_API_KEY xxx
```

Models: `deepseek-chat`, `deepseek-coder`

---

## Custom Endpoints

### Ollama

Run models locally with Ollama.

**Setup:**
1. Install Ollama: [ollama.com](https://ollama.com/)
2. Pull a model: `ollama pull qwen3.5:27b`
3. Configure Kunming Agent:

```bash
km model
# Select: Custom endpoint
# API base URL: http://localhost:11434/v1
# API key: ollama (or leave empty)
# Model name: qwen3.5:27b
```

### vLLM / SGLang

For production local serving.

**Configuration:**
```yaml
model:
  provider: custom
  base_url: http://localhost:8000/v1
  default: qwen3.5:27b
```

### LM Studio

**Configuration:**
```yaml
model:
  provider: custom
  base_url: http://localhost:1234/v1
  default: your-model-name
```

---

## Context Length Detection

Kunming Agent automatically detects model context lengths to optimize context usage.

### How It Works

1. On first use, the agent queries the provider's API for model metadata
2. Context length is stored in `config.yaml`
3. You can override manually if detection fails

### Override Context Length

```yaml
model:
  default: qwen3.5:27b
  context_length: 32768
```

### Per-Model Context Length

```yaml
custom_providers:
  - name: "Ollama"
    base_url: "http://localhost:11434/v1"
    models:
      qwen3.5:27b:
        context_length: 32768
      llama3.1:8b:
        context_length: 8192
```

### Supported Context Lengths

| Model | Context Length |
|-------|---------------|
| Claude 3.5 Sonnet | 200K |
| GPT-4 Turbo | 128K |
| Gemini 1.5 Pro | 1M |
| Llama 3.1 70B | 128K |
| Qwen 2.5 72B | 32K |
| DeepSeek V3 | 64K |

---

## Model Selection Tips

### For Coding

- **Claude** — Best for complex reasoning and code generation
- **GPT-4o** — Strong all-around, good for complex tasks
- **DeepSeek Coder** — Specialized for code

### For Speed

- **GPT-4o-mini** — Fast and affordable
- **Gemini 3 Flash** — Very fast, good quality
- **Llama 3.1 8B** — Great for simple tasks

### For Long Context

- **Claude 3.5 Sonnet** — 200K context
- **Gemini 1.5 Pro** — 1M context
- **DeepSeek V3** — 64K context

---

## Troubleshooting

### "Model not found"

**Cause:** Model identifier doesn't exist on your provider.

**Solution:**
```bash
# Check available models
km model
# Navigate to see available options

# Or check OpenRouter docs for correct model ID
```

### "Invalid API key"

**Cause:** Key is missing, expired, or for wrong provider.

**Solution:**
```bash
# Verify key is set
km config show | grep API_KEY

# Reset key
km config set OPENROUTER_API_KEY sk-or-v1-xxx
```

### "Rate limit exceeded"

**Cause:** Provider rate limit reached.

**Solution:**
- Wait and retry
- Use a slower model
- Upgrade provider plan
- Add backup provider

### "Context length mismatch"

**Cause:** Wrong context length detected.

**Solution:**
```bash
# Manually set context length
km config set model.context_length 32768

# Or edit config.yaml directly
```
