"""
HNSW Local Memory Plugin - Main Plugin Interface

Plugin interface for integrating with Kunming's memory system.

Based on: @claude-flow/memory V3.5 (migrated from agent/cognitive/memory/)
"""

import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from .types import MemoryEntryInput, MemoryType, SearchOptions
from .memory_store import MemoryStore, MemoryStoreConfig


@dataclass
class PluginConfig:
    """Plugin configuration"""
    dimensions: int = 1536
    auto_embed: bool = True
    namespace: str = "default"
    max_results: int = 10


class HnswMemoryPlugin:
    """
    HNSW Local Memory Plugin - Main interface for Kunming integration.

    This plugin provides vector-based semantic memory with HNSW indexing
    for fast similarity search.

    Example:
        ```python
        from plugins.memory.hnsw_local import HnswMemoryPlugin

        # Initialize plugin
        plugin = HnswMemoryPlugin()
        await plugin.initialize()

        # Store memory
        entry_id = await plugin.store(
            content="REST API design patterns",
            metadata={"tags": ["api", "design"]}
        )

        # Search memories
        results = await plugin.search("how to design APIs", k=5)
        ```
    """

    def __init__(self, config: Optional[PluginConfig] = None):
        """
        Initialize the plugin.

        Args:
            config: Plugin configuration
        """
        self.config = config or PluginConfig()
        self._store: Optional[MemoryStore] = None
        self._initialized = False

    async def initialize(self, embedding_generator=None) -> None:
        """
        Initialize the plugin.

        Args:
            embedding_generator: Optional function to generate embeddings from text
        """
        if self._initialized:
            return

        # Create store config
        store_config = MemoryStoreConfig(
            dimensions=self.config.dimensions,
            auto_embed=self.config.auto_embed,
            embedding_generator=embedding_generator,
            default_namespace=self.config.namespace
        )

        # Initialize store
        self._store = MemoryStore(config=store_config)
        await self._store.initialize()

        self._initialized = True

    async def store(
        self,
        content: str,
        key: Optional[str] = None,
        memory_type: str = "episodic",
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ) -> str:
        """
        Store a memory entry.

        Args:
            content: Memory content
            key: Optional key for the memory
            memory_type: Type of memory (episodic, semantic, procedural, working)
            metadata: Optional metadata dictionary
            tags: Optional list of tags

        Returns:
            Entry ID of the stored memory
        """
        if not self._initialized or not self._store:
            raise RuntimeError("Plugin not initialized")

        # Generate key if not provided
        if key is None:
            key = f"entry_{hashlib.sha256(content.encode()).hexdigest()[:16]}"

        # Create input
        input_data = MemoryEntryInput(
            key=key,
            content=content,
            type=MemoryType(memory_type),
            namespace=self.config.namespace,
            tags=tags or [],
            metadata=metadata or {}
        )

        # Store entry
        entry = await self._store.store(input_data)
        return entry.id

    async def retrieve(self, entry_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a memory entry by ID.

        Args:
            entry_id: Entry ID

        Returns:
            Memory entry as dictionary or None if not found
        """
        if not self._initialized or not self._store:
            raise RuntimeError("Plugin not initialized")

        entry = await self._store.retrieve(entry_id)
        if entry is None:
            return None

        return {
            "id": entry.id,
            "key": entry.key,
            "content": entry.content,
            "type": entry.type.value,
            "namespace": entry.namespace,
            "tags": entry.tags,
            "metadata": entry.metadata,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
            "access_count": entry.access_count
        }

    async def search(
        self,
        query: str,
        k: int = 10,
        threshold: Optional[float] = None,
        memory_type: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for memories using semantic search.

        Args:
            query: Search query
            k: Number of results to return
            threshold: Minimum similarity score (0-1)
            memory_type: Filter by memory type
            tags: Filter by tags

        Returns:
            List of search results
        """
        if not self._initialized or not self._store:
            raise RuntimeError("Plugin not initialized")

        # Create search options
        options = SearchOptions(
            k=k,
            threshold=threshold,
            namespace=self.config.namespace,
            memory_type=MemoryType(memory_type) if memory_type else None,
            tags=tags
        )

        # Search
        results = await self._store.search(query, options)

        # Format results
        return [
            {
                "id": r.entry.id,
                "key": r.entry.key,
                "content": r.entry.content,
                "type": r.entry.type.value,
                "score": r.score,
                "distance": r.distance,
                "metadata": r.entry.metadata,
                "tags": r.entry.tags
            }
            for r in results
        ]

    async def delete(self, entry_id: str) -> bool:
        """
        Delete a memory entry.

        Args:
            entry_id: Entry ID to delete

        Returns:
            True if deleted, False if not found
        """
        if not self._initialized or not self._store:
            raise RuntimeError("Plugin not initialized")

        return await self._store.delete(entry_id)

    async def clear(self) -> None:
        """Clear all memories"""
        if not self._initialized or not self._store:
            raise RuntimeError("Plugin not initialized")

        await self._store.clear()

    async def get_stats(self) -> Dict[str, Any]:
        """Get plugin statistics"""
        if not self._initialized or not self._store:
            return {"initialized": False}

        stats = await self._store.get_stats()
        return {
            "initialized": True,
            "total_entries": stats.total_entries,
            "total_vectors": stats.total_vectors,
            "avg_query_time_ms": stats.avg_query_time_ms,
            "cache_hit_rate": stats.cache_hit_rate
        }

    async def health_check(self) -> Dict[str, Any]:
        """Check plugin health"""
        if not self._initialized or not self._store:
            return {"healthy": False, "message": "Not initialized"}

        result = await self._store.health_check()
        return {
            "healthy": result.healthy,
            "component": result.component,
            "latency_ms": result.latency_ms,
            "message": result.message
        }

    async def shutdown(self) -> None:
        """Shutdown the plugin"""
        if self._store:
            await self._store.shutdown()
            self._store = None
        self._initialized = False


def create_memory_plugin(
    dimensions: int = 1536,
    auto_embed: bool = True,
    namespace: str = "default"
) -> HnswMemoryPlugin:
    """
    Create a memory plugin instance.

    Args:
        dimensions: Vector dimensions
        auto_embed: Whether to auto-generate embeddings
        namespace: Default namespace

    Returns:
        Configured HnswMemoryPlugin instance
    """
    config = PluginConfig(
        dimensions=dimensions,
        auto_embed=auto_embed,
        namespace=namespace
    )
    return HnswMemoryPlugin(config)
