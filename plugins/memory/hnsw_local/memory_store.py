"""
HNSW Local Memory Plugin - Memory Store

High-level memory storage interface with SQLite persistence and HNSW indexing.

Based on: @claude-flow/memory/src/index.ts (migrated from agent/cognitive/memory/)
"""

import json
import sqlite3
import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from numpy.typing import NDArray
import numpy as np

from .types import (
    MemoryEntry, MemoryEntryInput, SearchResult, SearchOptions,
    BackendStats, HealthCheckResult,
    MemoryType, AccessLevel,
    EmbeddingGenerator, MemoryEventHandler, MemoryEventType,
    generate_memory_id, PERFORMANCE_TARGETS
)
from .hnsw_index import HnswIndex


@dataclass
class MemoryStoreConfig:
    """Configuration for MemoryStore"""
    dimensions: int = 1536
    auto_embed: bool = True
    cache_enabled: bool = True
    cache_size: int = 1000
    hnsw_m: int = 16
    hnsw_ef_construction: int = 200
    default_namespace: str = "default"
    persistence_enabled: bool = True
    db_path: Optional[str] = None
    max_entries: int = 100000
    embedding_generator: Optional[EmbeddingGenerator] = None


class MemoryStore:
    """
    Memory Store - Main storage interface for HNSW Local Memory Plugin.

    This store provides:
    - Vector-based memory storage with HNSW indexing
    - SQLite persistence
    - Semantic search capabilities
    - Event-driven notifications

    Example:
        ```python
        # Initialize
        store = MemoryStore(config=MemoryStoreConfig(dimensions=1536))
        await store.initialize()

        # Store entry
        entry = await store.store(MemoryEntryInput(
            key='auth-patterns',
            content='OAuth 2.0 implementation patterns',
            tags=['auth', 'security']
        ))

        # Semantic search
        results = await store.search('user authentication best practices', k=5)
        ```
    """

    def __init__(self, config: Optional[MemoryStoreConfig] = None):
        """
        Initialize the memory store.

        Args:
            config: Store configuration. Uses defaults if not provided.
        """
        self.config = config or MemoryStoreConfig()
        self._index: Optional[HnswIndex] = None
        self._db: Optional[sqlite3.Connection] = None
        self._entries: Dict[str, MemoryEntry] = {}
        self._initialized = False
        self._event_handlers: List[MemoryEventHandler] = []
        self._query_count = 0
        self._query_time_total = 0.0

    async def initialize(self) -> None:
        """Initialize the memory store"""
        if self._initialized:
            return

        # Initialize HNSW index
        self._index = HnswIndex(
            dimensions=self.config.dimensions,
            m=self.config.hnsw_m,
            ef_construction=self.config.hnsw_ef_construction,
            metric="cosine"
        )

        # Initialize SQLite if persistence enabled
        if self.config.persistence_enabled:
            await self._init_database()
            await self._load_from_db()

        self._initialized = True
        await self._emit_event(MemoryEventType.INITIALIZED, {})

    async def _init_database(self) -> None:
        """Initialize SQLite database"""
        if self.config.db_path:
            db_path = Path(self.config.db_path)
        else:
            from kunming_constants import get_kunming_home
            db_path = get_kunming_home() / "hnsw_memory.db"

        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row

        # Create tables
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS memory_entries (
                id TEXT PRIMARY KEY,
                key TEXT NOT NULL,
                content TEXT NOT NULL,
                type TEXT NOT NULL,
                namespace TEXT NOT NULL DEFAULT 'default',
                tags TEXT,
                metadata TEXT,
                embedding BLOB,
                owner_id TEXT,
                access_level TEXT NOT NULL DEFAULT 'private',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                expires_at REAL,
                version INTEGER NOT NULL DEFAULT 1,
                access_count INTEGER NOT NULL DEFAULT 0,
                last_accessed_at REAL
            )
        """)

        # Create index
        self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_namespace ON memory_entries(namespace)
        """)
        self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_type ON memory_entries(type)
        """)
        self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_key ON memory_entries(key)
        """)

        self._db.commit()

    async def _load_from_db(self) -> None:
        """Load entries from database into memory"""
        if not self._db:
            return

        cursor = self._db.execute(
            "SELECT * FROM memory_entries WHERE expires_at IS NULL OR expires_at > ?",
            (time.time(),)
        )

        for row in cursor.fetchall():
            entry = self._row_to_entry(row)
            self._entries[entry.id] = entry

            # Add to HNSW index if has embedding
            if entry.embedding is not None and self._index:
                self._index.add(entry.id, entry.embedding)

    def _row_to_entry(self, row: sqlite3.Row) -> MemoryEntry:
        """Convert database row to MemoryEntry"""
        embedding = None
        if row['embedding']:
            embedding = np.frombuffer(row['embedding'], dtype=np.float32)

        return MemoryEntry(
            id=row['id'],
            key=row['key'],
            content=row['content'],
            type=MemoryType(row['type']),
            namespace=row['namespace'],
            tags=json.loads(row['tags']) if row['tags'] else [],
            metadata=json.loads(row['metadata']) if row['metadata'] else {},
            embedding=embedding,
            owner_id=row['owner_id'],
            access_level=AccessLevel(row['access_level']),
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            expires_at=row['expires_at'],
            version=row['version'],
            access_count=row['access_count'],
            last_accessed_at=row['last_accessed_at'] or row['created_at']
        )

    def _entry_to_row(self, entry: MemoryEntry) -> tuple:
        """Convert MemoryEntry to database row"""
        return (
            entry.id,
            entry.key,
            entry.content,
            entry.type.value,
            entry.namespace,
            json.dumps(entry.tags),
            json.dumps(entry.metadata),
            entry.embedding.tobytes() if entry.embedding is not None else None,
            entry.owner_id,
            entry.access_level.value,
            entry.created_at,
            entry.updated_at,
            entry.expires_at,
            entry.version,
            entry.access_count,
            entry.last_accessed_at
        )

    async def store(self, input_data: MemoryEntryInput) -> MemoryEntry:
        """
        Store a new memory entry.

        Args:
            input_data: Memory entry input data

        Returns:
            Created memory entry
        """
        if not self._initialized:
            raise RuntimeError("MemoryStore not initialized")

        # Generate embedding if needed
        embedding = input_data.embedding
        if embedding is None and self.config.auto_embed and self.config.embedding_generator:
            embedding = self.config.embedding_generator(input_data.content)

        # Create entry
        entry = MemoryEntry(
            id=generate_memory_id(),
            key=input_data.key,
            content=input_data.content,
            type=input_data.type,
            namespace=input_data.namespace,
            tags=input_data.tags,
            metadata=input_data.metadata,
            embedding=embedding,
            owner_id=input_data.owner_id,
            access_level=input_data.access_level,
            expires_at=input_data.expires_at
        )

        # Store in memory
        self._entries[entry.id] = entry

        # Add to HNSW index
        if embedding is not None and self._index:
            self._index.add(entry.id, embedding)

        # Persist to database
        if self._db:
            self._db.execute("""
                INSERT INTO memory_entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, self._entry_to_row(entry))
            self._db.commit()

        await self._emit_event(MemoryEventType.ENTRY_STORED, {"entry_id": entry.id})
        return entry

    async def retrieve(self, entry_id: str) -> Optional[MemoryEntry]:
        """
        Retrieve a memory entry by ID.

        Args:
            entry_id: Entry ID

        Returns:
            Memory entry or None if not found
        """
        entry = self._entries.get(entry_id)
        if entry:
            entry.access_count += 1
            entry.last_accessed_at = time.time()
        return entry

    async def search(
        self,
        query: str,
        options: Optional[SearchOptions] = None
    ) -> List[SearchResult]:
        """
        Search for memories using semantic search.

        Args:
            query: Search query text
            options: Search options

        Returns:
            List of search results
        """
        if not self._initialized:
            raise RuntimeError("MemoryStore not initialized")

        options = options or SearchOptions()
        start_time = time.time()

        # Generate query embedding
        query_embedding = None
        if self.config.embedding_generator:
            query_embedding = self.config.embedding_generator(query)

        if query_embedding is None or self._index is None:
            return []

        # Search HNSW index
        hnsw_results = self._index.search(
            query_embedding,
            k=options.k,
            threshold=options.threshold
        )

        # Build results
        results = []
        for hnsw_result in hnsw_results:
            entry = self._entries.get(hnsw_result.id)
            if entry:
                # Filter by namespace
                if options.namespace and entry.namespace != options.namespace:
                    continue
                # Filter by memory type
                if options.memory_type and entry.type != options.memory_type:
                    continue
                # Filter by tags
                if options.tags and not any(tag in entry.tags for tag in options.tags):
                    continue

                results.append(SearchResult(
                    entry=entry,
                    score=hnsw_result.score,
                    distance=1.0 - hnsw_result.score,
                    search_type="semantic"
                ))

        # Update stats
        self._query_count += 1
        self._query_time_total += time.time() - start_time

        return results

    async def delete(self, entry_id: str) -> bool:
        """
        Delete a memory entry.

        Args:
            entry_id: Entry ID to delete

        Returns:
            True if deleted, False if not found
        """
        if entry_id not in self._entries:
            return False

        # Remove from index
        if self._index:
            self._index.remove(entry_id)

        # Remove from memory
        del self._entries[entry_id]

        # Remove from database
        if self._db:
            self._db.execute("DELETE FROM memory_entries WHERE id = ?", (entry_id,))
            self._db.commit()

        await self._emit_event(MemoryEventType.ENTRY_DELETED, {"entry_id": entry_id})
        return True

    async def clear(self) -> None:
        """Clear all memory entries"""
        # Clear index
        if self._index:
            self._index.clear()

        # Clear memory
        self._entries.clear()

        # Clear database
        if self._db:
            self._db.execute("DELETE FROM memory_entries")
            self._db.commit()

        await self._emit_event(MemoryEventType.SHUTDOWN, {})

    async def get_stats(self) -> BackendStats:
        """Get memory store statistics"""
        avg_query_time = (self._query_time_total / self._query_count * 1000) if self._query_count > 0 else 0.0

        return BackendStats(
            total_entries=len(self._entries),
            total_vectors=self._index.size if self._index else 0,
            index_size_bytes=0,  # TODO: Calculate actual size
            avg_query_time_ms=avg_query_time,
            cache_hit_rate=0.0  # TODO: Implement cache tracking
        )

    async def health_check(self) -> HealthCheckResult:
        """Check memory store health"""
        start_time = time.time()

        try:
            # Basic health check
            healthy = self._initialized and (self._index is not None)
            latency_ms = (time.time() - start_time) * 1000

            return HealthCheckResult(
                healthy=healthy,
                component="memory_store",
                latency_ms=latency_ms,
                message="Healthy" if healthy else "Not initialized"
            )
        except Exception as e:
            return HealthCheckResult(
                healthy=False,
                component="memory_store",
                latency_ms=(time.time() - start_time) * 1000,
                message=str(e)
            )

    def add_event_handler(self, handler: MemoryEventHandler) -> None:
        """Add an event handler"""
        self._event_handlers.append(handler)

    async def _emit_event(self, event_type: MemoryEventType, data: Dict[str, Any]) -> None:
        """Emit an event to all handlers"""
        for handler in self._event_handlers:
            try:
                handler(event_type, data)
            except Exception:
                pass  # Ignore handler errors

    async def shutdown(self) -> None:
        """Shutdown the memory store"""
        if self._db:
            self._db.close()
            self._db = None

        self._initialized = False
        await self._emit_event(MemoryEventType.SHUTDOWN, {})
