"""
HNSW Local Memory Plugin - Vector-based semantic memory with HNSW indexing.

This plugin provides:
- HNSW vector index for efficient similarity search (150x-12,500x faster)
- SQLite persistence for memory storage
- Semantic search capabilities
- Cross-session memory sharing
- Event-driven architecture

Integration with Kunming:
    The memory system can be integrated with Kunming's existing MemoryManager
    as a MemoryProvider, enhancing FTS5 search with semantic capabilities.

Example:
    ```python
    from plugins.memory.hnsw_local import HnswMemoryPlugin

    # Create plugin instance
    memory = HnswMemoryPlugin()
    await memory.initialize()

    # Store memory
    entry_id = await memory.store(
        content="REST API design patterns",
        metadata={"tags": ["api", "design"]}
    )

    # Semantic search
    results = await memory.search("how to design APIs", k=5)
    ```

Based on: @claude-flow/memory V3.5 (migrated from agent/cognitive/memory/)
"""

from .types import (
    # Enums
    MemoryType,
    AccessLevel,
    DistanceMetric,
    MemoryEventType,

    # Data Classes
    MemoryEntry,
    MemoryEntryInput,
    SearchResult,
    SearchOptions,

    # Type Aliases
    EmbeddingGenerator,
    MemoryEventHandler,

    # Utilities
    generate_memory_id,
)

from .hnsw_index import (
    HnswIndex,
    HnswSearchResult,
    cosine_similarity,
    dot_product,
    euclidean_distance,
)

from .memory_store import (
    MemoryStore,
    MemoryStoreConfig,
)

from .plugin import (
    HnswMemoryPlugin,
    create_memory_plugin,
)

__version__ = "3.5.0"

__all__ = [
    # Types
    "MemoryType",
    "AccessLevel",
    "DistanceMetric",
    "MemoryEventType",
    "MemoryEntry",
    "MemoryEntryInput",
    "SearchResult",
    "SearchOptions",
    "EmbeddingGenerator",
    "MemoryEventHandler",
    "generate_memory_id",

    # HNSW Index
    "HnswIndex",
    "HnswSearchResult",
    "cosine_similarity",
    "dot_product",
    "euclidean_distance",

    # Memory Store
    "MemoryStore",
    "MemoryStoreConfig",

    # Plugin
    "HnswMemoryPlugin",
    "create_memory_plugin",
]
