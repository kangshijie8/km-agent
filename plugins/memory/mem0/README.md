# Mem0 Memory Plugin

[Mem0](https://github.com/mem0ai/mem0) is an open-source memory layer for AI applications. This plugin integrates Mem0 with Kunming Agent, enabling persistent memory across conversations.

## Installation

```bash
pip install mem0ai
```

Or install with the optional dependency:

```bash
pip install "kunming-agent[mem0]"
```

## Configuration

Add to your `~/.kunming/config.yaml`:

```yaml
memory:
  provider: mem0
  config:
    api_key: your-mem0-api-key  # Or set MEM0_API_KEY env var
    user_id: kunming-user        # Optional: customize user ID
    agent_id: kunming            # Optional: customize agent ID
```

Or use environment variables:

```bash
export MEM0_API_KEY=your-api-key
export MEM0_USER_ID=kunming-user
export MEM0_AGENT_ID=kunming
```

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `api_key` | - | Mem0 API key (required) |
| `user_id` | `kunming-user` | User identifier on Mem0 |
| `agent_id` | `kunming` | Agent identifier |

## How It Works

The Mem0 plugin:
1. Stores conversation history in Mem0's memory system
2. Retrieves relevant memories at the start of each conversation
3. Automatically adds memories based on conversation context
4. Supports both explicit (`/remember`) and implicit memory storage

## Memory Types

- **Episodic**: Specific events and interactions
- **Semantic**: Facts and concepts about the user
- **Procedural**: How-to knowledge and preferences

## Usage

Once configured, memory is automatic. Use slash commands to manage:

- `/remember <text>` - Explicitly store a memory
- `/recall [query]` - Retrieve relevant memories
- `/forget <query>` - Remove specific memories

## API Reference

See [Mem0 Documentation](https://docs.mem0.ai/) for advanced configuration options.
