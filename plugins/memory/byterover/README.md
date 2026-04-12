# ByteRover Memory Plugin

ByteRover provides persistent, queryable memory storage for Kunming Agent with full-text search capabilities and efficient data retrieval.

## Installation

```bash
pip install "kunming-agent[byterover]"
```

## Configuration

Add to your `~/.kunming/config.yaml`:

```yaml
memory:
  provider: byterover
  config:
    db_path: ~/.kunming/byterover.db    # SQLite database path
    index_fields:                       # Fields to index for search
      - content
      - metadata.tags
    max_results: 10                     # Default search result limit
    enable_fts: true                    # Enable full-text search
```

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `db_path` | `~/.kunming/byterover.db` | SQLite database file path |
| `index_fields` | `["content"]` | Fields to include in search index |
| `max_results` | `10` | Default number of search results |
| `enable_fts` | `true` | Enable SQLite FTS5 for full-text search |

## How It Works

ByteRover stores memories in a local SQLite database with:

1. **Structured Storage**: JSON documents with metadata
2. **Full-Text Search**: FTS5 index for fast text queries
3. **Tagging System**: Categorize memories with custom tags
4. **Temporal Queries**: Search by time ranges

## Features

### Document Storage

Store arbitrary JSON documents:

```json
{
  "content": "User prefers Python for data processing",
  "metadata": {
    "tags": ["preference", "python"],
    "timestamp": "2026-01-15T10:30:00Z",
    "importance": "high"
  }
}
```

### Full-Text Search

Search across all indexed fields:

```python
# Search for "python" in content
results = memory.search("python", field="content")

# Search all indexed fields
results = memory.search("async patterns")

# Tag-based search
results = memory.search("preference", field="metadata.tags")
```

### Temporal Queries

Find memories from specific time periods:

```python
# Last 24 hours
results = memory.since(hours=24)

# Specific date range
results = memory.between("2026-01-01", "2026-01-31")

# Most recent N memories
results = memory.recent(n=50)
```

## Usage

Configure in your config file:

```yaml
memory:
  provider: byterover
  config:
    db_path: ~/.kunming/byterover.db
    index_fields:
      - content
      - metadata.summary
    max_results: 15
```

Use slash commands for manual control:

- `/remember <text> [#tag1 #tag2]` - Store with tags
- `/search <query>` - Full-text search
- `/recent [n]` - Show recent memories
- `/tags` - List all tags

## Advanced Features

### Custom Schemas

Define custom document structures:

```yaml
memory:
  provider: byterover
  config:
    schema:
      type: object
      properties:
        content: { type: string }
        metadata:
          type: object
          properties:
            priority: { type: integer }
            category: { type: string }
```

### Backup and Export

```bash
# Export all memories to JSON
km memory export --format json --output memories.json

# Backup database
cp ~/.kunming/byterover.db ~/.kunming/byterover.db.backup
```

### Migration

Import from other memory providers:

```bash
# Import from JSON export
km memory import --source memories.json --provider byterover
```

## Architecture

```
Kunming Agent
      |
      v
ByteRover Plugin
      |
      +---> SQLite Database
      |       +-- memories table
      |       +-- fts5 virtual table
      |       +-- tags index
      |
      +---> Query Engine
              +-- Full-text search
              +-- Tag filtering
              +-- Temporal queries
```

## Performance

- Sub-millisecond queries with proper indexing
- Handles 100K+ memories efficiently
- Automatic query optimization
- Connection pooling for concurrent access

## Storage Format

SQLite schema:

```sql
CREATE TABLE memories (
    id INTEGER PRIMARY KEY,
    content TEXT NOT NULL,
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE memories_fts USING fts5(
    content,
    content='memories',
    content_rowid='id'
);
```
