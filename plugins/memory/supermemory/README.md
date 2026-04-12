# SuperMemory Plugin

SuperMemory is an advanced memory system for Kunming Agent that provides intelligent memory management with automatic categorization, semantic search, and long-term persistence.

## Installation

```bash
pip install "kunming-agent[supermemory]"
```

Or install the dependencies directly:

```bash
pip install supermemory-client
```

## Configuration

Add to your `~/.kunming/config.yaml`:

```yaml
memory:
  provider: supermemory
  config:
    api_key: your-supermemory-api-key    # Or set SUPERMEMORY_API_KEY env var
    base_url: https://api.supermemory.ai  # Optional: custom endpoint
    container_tag: kunming                 # Container tag for search/writes
    auto_categorize: true                  # Auto-categorize memories
    sync_interval: 300                     # Sync interval in seconds
```

Or use environment variables:

```bash
export SUPERMEMORY_API_KEY=your-api-key
export SUPERMEMORY_BASE_URL=https://api.supermemory.ai
export SUPERMEMORY_CONTAINER_TAG=kunming
```

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `api_key` | - | SuperMemory API key (required) |
| `base_url` | `https://api.supermemory.ai` | SuperMemory API base URL |
| `container_tag` | `kunming` | Container tag used for search and writes. Supports `{identity}` template for profile-scoped tags (e.g. `kunming-{identity}` -> `kunming-coder`). |
| `auto_categorize` | `true` | Automatically categorize memories by topic |
| `sync_interval` | `300` | Seconds between background syncs |

## How It Works

SuperMemory provides a comprehensive memory system:

1. **Storage**: Memories stored with rich metadata and embeddings
2. **Categorization**: Automatic topic extraction and tagging
3. **Retrieval**: Semantic search with relevance ranking
4. **Sync**: Background synchronization for persistence

## Features

### Automatic Categorization

Memories are automatically tagged with topics:

```json
{
  "content": "User prefers async/await over callbacks in Python",
  "categories": ["python", "async", "preferences"],
  "confidence": 0.95
}
```

### Semantic Search

Find memories by meaning, not just keywords:

```python
# Search for "concurrency" will find "async/await" memories
results = memory.search("how to handle concurrent tasks")
```

### Profile-Scoped Containers

Use `{identity}` in the `container_tag` to scope memories per Kunming profile:

```yaml
memory:
  provider: supermemory
  config:
    container_tag: "kunming-{identity}"
```

For a profile named `coder`, this resolves to `kunming-coder`. The default profile resolves to `kunming-default`. Without `{identity}`, all profiles share the same container.

## Usage

Once configured, SuperMemory integration is automatic. The plugin will:
- Store conversation memories with automatic categorization
- Retrieve relevant context for new conversations
- Sync memories in the background

Configure in your config file:

```yaml
memory:
  provider: supermemory
  config:
    container_tag: kunming
    auto_categorize: true
```

Use slash commands for manual control:

- `/remember <text>` - Store a memory
- `/recall [query]` - Search memories
- `/categories` - List memory categories
- `/sync` - Force immediate sync

## Advanced Features

### Custom Categories

Define your own category schema:

```yaml
memory:
  provider: supermemory
  config:
    custom_categories:
      - name: "code_patterns"
        patterns: ["def ", "class ", "import "]
      - name: "preferences"
        patterns: ["prefer", "like", "dislike"]
```

### Memory Relationships

Link related memories together:

```bash
# Create a relationship
/remember "API rate limit is 1000/hour" --related "API authentication"

# Find related memories
/related "API rate limit"
```

### Importance Scoring

Memories are scored by importance:

```yaml
memory:
  provider: supermemory
  config:
    importance_signals:
      - explicit_mark  # User used /remember
      - repeated_topic # Mentioned multiple times
      - action_item    # Contains TODO/action words
```

## Architecture

```
Kunming Agent
      |
      v
SuperMemory Plugin
      |
      +---> Categorization Engine
      |       +-- Topic extraction
      |       +-- Tag generation
      |
      +---> Memory Store
      |       +-- Vector embeddings
      |       +-- Metadata index
      |
      +---> Retrieval Engine
              +-- Semantic search
              +-- Relevance ranking
              +-- Context assembly
```

## API Reference

See [SuperMemory Documentation](https://docs.supermemory.ai/) for advanced usage.

## Default Configuration

```yaml
memory:
  provider: supermemory
  config:
    container_tag: kunming,
```
