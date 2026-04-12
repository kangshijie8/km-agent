"""
HNSW Local Memory Plugin - Type Definitions

Type definitions for the vector memory system with HNSW indexing.
Supports 150x-12,500x faster vector search compared to brute-force approaches.

Based on: @claude-flow/memory/src/types.ts (migrated from agent/cognitive/memory/)
"""

from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
import numpy as np
from numpy.typing import NDArray


# ===== Enums =====

class MemoryType(Enum):
    """Memory entry type classification"""
    EPISODIC = "episodic"      # Time-based experiences and events
    SEMANTIC = "semantic"      # Facts, concepts, and knowledge
    PROCEDURAL = "procedural"  # How-to knowledge and skills
    WORKING = "working"        # Short-term operational memory
    CACHE = "cache"            # Temporary cached data


class AccessLevel(Enum):
    """Access level for memory entries"""
    PRIVATE = "private"    # Only owner can access
    TEAM = "team"          # Team members can access
    PUBLIC = "public"      # Publicly accessible
    SYSTEM = "system"      # System-level access


class DistanceMetric(Enum):
    """Distance metrics for vector similarity search"""
    COSINE = "cosine"      # Cosine similarity (default)
    EUCLIDEAN = "euclidean"  # Euclidean distance (L2)
    DOT = "dot"            # Dot product
    MANHATTAN = "manhattan"  # Manhattan distance (L1)


class MemoryEventType(Enum):
    """Event types for memory system"""
    ENTRY_STORED = "entry:stored"
    ENTRY_UPDATED = "entry:updated"
    ENTRY_DELETED = "entry:deleted"
    CACHE_HIT = "cache:hit"
    CACHE_MISS = "cache:miss"
    INITIALIZED = "initialized"
    SHUTDOWN = "shutdown"


# ===== Data Classes =====

@dataclass
class MemoryEntry:
    """Core memory entry structure with vector embedding support"""
    id: str
    key: str
    content: str
    type: MemoryType
    namespace: str = "default"
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[NDArray] = None
    owner_id: Optional[str] = None
    access_level: AccessLevel = AccessLevel.PRIVATE
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    updated_at: float = field(default_factory=lambda: datetime.now().timestamp())
    expires_at: Optional[float] = None
    version: int = 1
    access_count: int = 0
    last_accessed_at: float = field(default_factory=lambda: datetime.now().timestamp())


@dataclass
class MemoryEntryInput:
    """Input for creating a new memory entry"""
    key: str
    content: str
    type: MemoryType = MemoryType.EPISODIC
    namespace: str = "default"
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[NDArray] = None
    owner_id: Optional[str] = None
    access_level: AccessLevel = AccessLevel.PRIVATE
    expires_at: Optional[float] = None


@dataclass
class SearchResult:
    """Result from memory search"""
    entry: MemoryEntry
    score: float
    distance: float
    search_type: str = "semantic"


@dataclass
class SearchOptions:
    """Options for memory search"""
    k: int = 10
    threshold: Optional[float] = None
    namespace: Optional[str] = None
    memory_type: Optional[MemoryType] = None
    tags: Optional[List[str]] = None
    include_metadata: bool = True


@dataclass
class BackendStats:
    """Statistics for memory backend"""
    total_entries: int
    total_vectors: int
    index_size_bytes: int
    avg_query_time_ms: float
    cache_hit_rate: float


@dataclass
class HealthCheckResult:
    """Health check result for memory system"""
    healthy: bool
    component: str
    latency_ms: float
    message: str


# ===== Type Aliases =====

EmbeddingGenerator = Callable[[str], NDArray[np.float32]]
MemoryEventHandler = Callable[[MemoryEventType, Dict[str, Any]], None]


# ===== Utilities =====

def generate_memory_id() -> str:
    """Generate a unique memory entry ID"""
    import uuid
    return f"mem_{uuid.uuid4().hex[:16]}"


# ===== Performance Targets =====

PERFORMANCE_TARGETS = {
    "search_latency_p50_ms": 1.0,
    "search_latency_p99_ms": 10.0,
    "insertion_latency_ms": 5.0,
    "cache_hit_rate": 0.85,
    "max_entries": 100000,
}
