# HNSW Local Memory Plugin

Local vector-based memory plugin with HNSW (Hierarchical Navigable Small World) indexing for fast semantic search.

## Features

- **HNSW Vector Index**: 150x-12,500x faster semantic search compared to brute-force
- **SQLite Persistence**: Persistent storage with SQLite backend
- **Semantic Search**: Vector similarity search for finding relevant memories
- **Multiple Memory Types**: Support for episodic, semantic, procedural, and working memory
- **Event-Driven Architecture**: Hook into memory events for custom processing

## Installation

This plugin is included with Kunming Agent. No additional installation required.

Dependencies:
- numpy

## Usage

```python
from plugins.memory.hnsw_local import HnswMemoryPlugin

# Initialize plugin
plugin = HnswMemoryPlugin()

# Provide an embedding generator function
async def embed_text(text: str):
    # Your embedding logic here
    return embedding_vector

await plugin.initialize(embedding_generator=embed_text)

# Store a memory
entry_id = await plugin.store(
    content="REST API design patterns",
    metadata={"tags": ["api", "design"]},
    tags=["api", "rest"]
)

# Search memories
results = await plugin.search("how to design APIs", k=5)
for result in results:
    print(f"{result['score']:.3f}: {result['content']}")

# Retrieve a specific memory
memory = await plugin.retrieve(entry_id)

# Delete a memory
await plugin.delete(entry_id)

# Get stats
stats = await plugin.get_stats()
print(f"Total entries: {stats['total_entries']}")

# Shutdown
await plugin.shutdown()
```

## Configuration

Edit `plugin.yaml` to configure:

```yaml
config:
  dimensions: 1536          # Vector dimensions
  auto_embed: true          # Auto-generate embeddings
  cache_enabled: true       # Enable caching
  cache_size: 1000         # Cache size
  hnsw_m: 16               # HNSW max neighbors
  hnsw_ef_construction: 200 # HNSW construction parameter
  persistence_enabled: true # Enable SQLite persistence
  max_entries: 100000      # Maximum entries
```

## Architecture

```
plugins/memory/hnsw_local/
├── __init__.py          # Package exports
├── plugin.yaml          # Plugin configuration
├── types.py            # Type definitions
├── hnsw_index.py       # HNSW vector index
├── memory_store.py     # SQLite storage layer
├── plugin.py           # Main plugin interface
└── README.md           # Documentation
```

## Migration Notes

This plugin was migrated from `agent/cognitive/memory/` as part of the consolidation effort
to eliminate duplicate implementations and centralize memory plugins in `plugins/memory/`.

## License

Same as Kunming Agent
