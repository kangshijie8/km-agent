# RetainDB Memory Plugin

RetainDB provides persistent, queryable memory storage with automatic retention policies for Kunming Agent, ensuring important memories are preserved while managing storage efficiently.

## Installation

```bash
pip install "kunming-agent[retaindb]"
```

Or install the dependencies directly:

```bash
pip install sqlite3  # Usually included in Python stdlib
```

## Configuration

Add to your `~/.kunming/config.yaml`:

```yaml
memory:
  provider: retaindb
  config:
    db_path: ~/.kunming/retaindb.db     # SQLite database path
    retention_days: 365                  # How long to keep memories
    max_memories: 50000                  # Maximum memories before pruning
    prune_strategy: lru                  # lru, lfu, or importance
    importance_boost: 2.0                # Multiplier for marked memories
    compression: true                    # Compress old memories
    compression_threshold_days: 30       # Compress after N days
```

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `db_path` | `~/.kunming/retaindb.db` | SQLite database file path |
| `retention_days` | `365` | Days to retain memories before eligible for deletion |
| `max_memories` | `50000` | Maximum memories before pruning triggers |
| `prune_strategy` | `lru` | Strategy: `lru` (least recent), `lfu` (least frequent), `importance` |
| `importance_boost` | `2.0` | Score multiplier for important memories |
| `compression` | `true` | Compress older memories to save space |
| `compression_threshold_days` | `30` | Days before compression applies |

## How It Works

RetainDB manages memory lifecycle automatically:

1. **Storage**: All memories stored with metadata (timestamp, access count, importance)
2. **Scoring**: Each memory has a retention score based on age, access frequency, and importance
3. **Pruning**: When storage limits hit, lowest-scored memories are removed
4. **Compression**: Old memories are summarized to save space

## Features

### Retention Policies

Configure how memories are preserved:

```yaml
# Keep frequently accessed memories
prune_strategy: lfu

# Keep recently accessed memories
prune_strategy: lru

# Keep explicitly marked important memories
prune_strategy: importance
```

### Automatic Compression

Old memories are compressed to save space:

```yaml
memory:
  provider: retaindb
  config:
    compression: true
    compression_threshold_days: 14  # Compress after 2 weeks
    compression_ratio: 0.5          # Target 50% size reduction
```

### Importance Marking

Explicitly preserve critical memories:

```bash
# Mark as important (survives pruning)
/remember "Critical API key: xyz789" --important

# Query importance
/search "API key" --important-only
```

## Usage

Configure in your config file:

```yaml
memory:
  provider: retaindb
  config:
    retention_days: 180
    max_memories: 10000
    prune_strategy: lru
```

Use slash commands for manual control:

- `/remember <text>` - Store a memory
- `/remember <text> --important` - Store with importance flag
- `/search <query>` - Search memories
- `/stats` - Show storage statistics
- `/prune` - Manually trigger pruning

## Advanced Configuration

### Custom Scoring Function

Define how retention scores are calculated:

```yaml
memory:
  provider: retaindb
  config:
    scoring:
      age_weight: 0.3
      frequency_weight: 0.4
      importance_weight: 0.3
```

### Tiered Storage

Different retention for different memory types:

```yaml
memory:
  provider: retaindb
  config:
    tiers:
      - name: critical
        retention_days: 999999
        max_count: 1000
      - name: normal
        retention_days: 90
        max_count: 40000
      - name: temporary
        retention_days: 7
        max_count: 5000
```

### Scheduled Maintenance

Automatic cleanup at intervals:

```yaml
memory:
  provider: retaindb
  config:
    maintenance:
      enabled: true
      interval_hours: 24
      prune_on_maintenance: true
      compress_on_maintenance: true
```

## Architecture

```
New Memory
    |
    v
+-------------------+
| Importance Check  |----> Marked important?
+-------------------+           |
        |                       v
        |               +-------------------+
        |               | High Score        |
        v               +-------------------+
+-------------------+           |
| Score Calculation |           v
| - Age             |   +-------------------+
| - Frequency       |   | Priority Queue    |
| - Importance      |   +-------------------+
+-------------------+           |
        |                       v
        v               +-------------------+
+-------------------+   | Pruning Engine    |
| Storage           |<--| (when full)       |
| - SQLite          |   +-------------------+
| - Compressed      |           |
| - Full-text       |           v
+-------------------+   +-------------------+
        |               | Compression       |
        |               | (old memories)    |
        v               +-------------------+
+-------------------+
| Query Interface   |
+-------------------+
```

## Storage Statistics

View storage metrics:

```bash
$ km memory stats

RetainDB Statistics:
  Total memories: 12,456
  Compressed: 8,234 (66%)
  Important: 234
  Storage used: 45.2 MB
  
  By age:
    < 7 days: 1,234
    7-30 days: 3,456
    30-90 days: 5,678
    > 90 days: 2,088
  
  Pruning status:
    Last prune: 2026-01-14 10:30
    Next scheduled: 2026-01-15 10:30
    Memories pruned (last run): 123
```

## Migration

Import from other memory providers:

```bash
# Export existing memories
km memory export --provider <old> --output memories.json

# Import to RetainDB
km memory import --provider retaindb --source memories.json

# Mark important memories during import
km memory import --provider retaindb --source memories.json --mark-important
```
