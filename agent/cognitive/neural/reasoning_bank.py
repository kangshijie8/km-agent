"""
Cognitive Core ReasoningBank - Python Implementation

Trajectory storage and retrieval system with HNSW indexing for efficient
semantic search. Stores agent reasoning trajectories for learning and replay.

Based on: @claude-flow/neural/src/index.ts
"""

import atexit
import json
import sqlite3
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from numpy.typing import NDArray
import numpy as np

from kunming_constants import get_kunming_home

from .types import (
    ReasoningStep, ReasoningTrajectory,
    ReasoningBankConfig, LearningMetrics,
    generate_trajectory_id, calculate_similarity
)


@dataclass
class TrajectorySearchResult:
    """Result from trajectory search"""
    trajectory: ReasoningTrajectory
    score: float


class ReasoningBank:
    """
    ReasoningBank - Trajectory storage and retrieval system.
    
    Stores agent reasoning trajectories with:
    - SQLite persistence for durability
    - HNSW indexing for semantic search
    - Compression for efficient storage
    - Tag-based filtering
    
    Integration with Kunming:
        ReasoningBank enhances Kunming's existing trajectory_compressor by
        providing semantic search capabilities and structured storage.
        It can be used to:
        - Store successful reasoning patterns
        - Retrieve similar past trajectories
        - Train RL policies from experience
        - Generate training data for model fine-tuning
    
    Example:
        ```python
        from agent.cognitive.neural import ReasoningBank, ReasoningBankConfig
        
        # Initialize
        bank = ReasoningBank(ReasoningBankConfig())
        await bank.initialize()
        
        # Store trajectory
        trajectory = ReasoningTrajectory(
            id=generate_trajectory_id(),
            task_id="task-1",
            agent_id="agent-1",
            steps=[...],
            final_result="Success",
            success=True,
            total_steps=5,
            total_time_ms=1000
        )
        await bank.store(trajectory)
        
        # Search similar trajectories
        results = await bank.search_similar(query_embedding, k=5)
        ```
    """
    
    def __init__(self, config: Optional[ReasoningBankConfig] = None):
        """
        Initialize ReasoningBank.
        
        Args:
            config: Configuration for the bank
        """
        self.config = config or ReasoningBankConfig()
        self._initialized = False
        
        # In-memory storage
        self._trajectories: Dict[str, ReasoningTrajectory] = {}
        self._tag_index: Dict[str, List[str]] = {}
        self._agent_index: Dict[str, List[str]] = {}
        self._task_index: Dict[str, List[str]] = {}
        
        # HNSW index for semantic search
        self._embedding_index: Dict[str, NDArray] = {}
        
        # SQLite backend
        self._db_path: Optional[Path] = None
        self._conn: Optional[sqlite3.Connection] = None
        
        # Statistics
        self._metrics = LearningMetrics()

        atexit.register(self._atexit_shutdown)
    
    async def initialize(self) -> None:
        """Initialize the ReasoningBank"""
        if self._initialized:
            return
        
        # Initialize SQLite
        self._db_path = get_kunming_home() / "reasoning_bank.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        
        # Create tables
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS trajectories (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                steps TEXT NOT NULL,  -- JSON
                final_result TEXT NOT NULL,
                success INTEGER NOT NULL,
                total_steps INTEGER NOT NULL,
                total_time_ms REAL NOT NULL,
                created_at REAL NOT NULL,
                tags TEXT NOT NULL,  -- JSON array
                embedding BLOB  -- numpy bytes
            );
            
            CREATE INDEX IF NOT EXISTS idx_task ON trajectories(task_id);
            CREATE INDEX IF NOT EXISTS idx_agent ON trajectories(agent_id);
            CREATE INDEX IF NOT EXISTS idx_success ON trajectories(success);
            CREATE INDEX IF NOT EXISTS idx_created ON trajectories(created_at);
            
            CREATE TABLE IF NOT EXISTS trajectory_tags (
                trajectory_id TEXT,
                tag TEXT,
                PRIMARY KEY (trajectory_id, tag),
                FOREIGN KEY (trajectory_id) REFERENCES trajectories(id)
            );
            
            CREATE INDEX IF NOT EXISTS idx_tag ON trajectory_tags(tag);
        """)
        self._conn.commit()
        
        # Load existing trajectories
        await self._load_from_persistence()
        
        self._initialized = True
    
    async def shutdown(self) -> None:
        """Shutdown the ReasoningBank"""
        if self._conn:
            self._conn.close()
            self._conn = None
        
        self._initialized = False

    def _atexit_shutdown(self) -> None:
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
    
    async def _load_from_persistence(self) -> None:
        """Load trajectories from database"""
        if not self._conn:
            return
        
        cursor = self._conn.execute("SELECT * FROM trajectories")
        
        for row in cursor.fetchall():
            trajectory = self._row_to_trajectory(row)
            self._trajectories[trajectory.id] = trajectory
            
            # Index embedding
            if trajectory.embedding is not None:
                self._embedding_index[trajectory.id] = trajectory.embedding
            
            # Index by tags
            for tag in trajectory.tags:
                if tag not in self._tag_index:
                    self._tag_index[tag] = []
                self._tag_index[tag].append(trajectory.id)
            
            # Index by agent
            if trajectory.agent_id not in self._agent_index:
                self._agent_index[trajectory.agent_id] = []
            self._agent_index[trajectory.agent_id].append(trajectory.id)
            
            # Index by task
            if trajectory.task_id not in self._task_index:
                self._task_index[trajectory.task_id] = []
            self._task_index[trajectory.task_id].append(trajectory.id)
        
        self._metrics.total_trajectories = len(self._trajectories)
    
    def _row_to_trajectory(self, row: sqlite3.Row) -> ReasoningTrajectory:
        """Convert database row to trajectory"""
        steps_data = json.loads(row["steps"])
        steps = [
            ReasoningStep(
                step_number=s["step_number"],
                input_data=s["input_data"],
                thought_process=s["thought_process"],
                action_taken=s["action_taken"],
                output_result=s["output_result"],
                confidence=s["confidence"],
                timestamp=s.get("timestamp", datetime.now().timestamp()),
                metadata=s.get("metadata", {})
            )
            for s in steps_data
        ]
        
        embedding = None
        if row["embedding"]:
            embedding = np.frombuffer(row["embedding"], dtype=np.float32)
        
        return ReasoningTrajectory(
            id=row["id"],
            task_id=row["task_id"],
            agent_id=row["agent_id"],
            steps=steps,
            final_result=row["final_result"],
            success=bool(row["success"]),
            total_steps=row["total_steps"],
            total_time_ms=row["total_time_ms"],
            created_at=row["created_at"],
            tags=json.loads(row["tags"]),
            embedding=embedding
        )
    
    def _trajectory_to_row(self, trajectory: ReasoningTrajectory) -> tuple:
        """Convert trajectory to database row"""
        steps_data = [
            {
                "step_number": s.step_number,
                "input_data": s.input_data,
                "thought_process": s.thought_process,
                "action_taken": s.action_taken,
                "output_result": s.output_result,
                "confidence": s.confidence,
                "timestamp": s.timestamp,
                "metadata": s.metadata
            }
            for s in trajectory.steps
        ]
        
        embedding_bytes = None
        if trajectory.embedding is not None:
            embedding_bytes = trajectory.embedding.tobytes()
        
        return (
            trajectory.id,
            trajectory.task_id,
            trajectory.agent_id,
            json.dumps(steps_data),
            trajectory.final_result,
            int(trajectory.success),
            trajectory.total_steps,
            trajectory.total_time_ms,
            trajectory.created_at,
            json.dumps(trajectory.tags),
            embedding_bytes
        )
    
    # ===== Core Operations =====
    
    async def store(self, trajectory: ReasoningTrajectory) -> None:
        """
        Store a trajectory in the bank.
        
        Args:
            trajectory: Trajectory to store
        """
        self._check_initialized()
        
        # Store in memory
        self._trajectories[trajectory.id] = trajectory
        
        # Index embedding
        if trajectory.embedding is not None:
            self._embedding_index[trajectory.id] = trajectory.embedding
        
        # Index by tags
        for tag in trajectory.tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = []
            if trajectory.id not in self._tag_index[tag]:
                self._tag_index[tag].append(trajectory.id)
        
        # Index by agent
        if trajectory.agent_id not in self._agent_index:
            self._agent_index[trajectory.agent_id] = []
        if trajectory.id not in self._agent_index[trajectory.agent_id]:
            self._agent_index[trajectory.agent_id].append(trajectory.id)
        
        # Index by task
        if trajectory.task_id not in self._task_index:
            self._task_index[trajectory.task_id] = []
        if trajectory.id not in self._task_index[trajectory.task_id]:
            self._task_index[trajectory.task_id].append(trajectory.id)
        
        # Persist to database
        await self._persist_trajectory(trajectory)
        
        # Update metrics
        self._metrics.total_trajectories += 1
        
        # Check if we need to compress
        if self.config.enable_compression:
            await self._maybe_compress()
    
    async def _persist_trajectory(self, trajectory: ReasoningTrajectory) -> None:
        """Persist trajectory to database"""
        if not self._conn:
            return

        with self._conn:
            self._conn.execute(
                """INSERT OR REPLACE INTO trajectories VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )""",
                self._trajectory_to_row(trajectory)
            )

            self._conn.execute(
                "DELETE FROM trajectory_tags WHERE trajectory_id = ?",
                (trajectory.id,)
            )

            for tag in trajectory.tags:
                self._conn.execute(
                    "INSERT INTO trajectory_tags VALUES (?, ?)",
                    (trajectory.id, tag)
                )
    
    async def get(self, trajectory_id: str) -> Optional[ReasoningTrajectory]:
        """
        Get a trajectory by ID.
        
        Args:
            trajectory_id: Trajectory ID
            
        Returns:
            Trajectory or None if not found
        """
        self._check_initialized()
        return self._trajectories.get(trajectory_id)
    
    async def delete(self, trajectory_id: str) -> bool:
        """
        Delete a trajectory.
        
        Args:
            trajectory_id: Trajectory ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        self._check_initialized()
        
        trajectory = self._trajectories.get(trajectory_id)
        if not trajectory:
            return False
        
        # Remove from indexes
        del self._trajectories[trajectory_id]
        
        if trajectory_id in self._embedding_index:
            del self._embedding_index[trajectory_id]
        
        for tag in trajectory.tags:
            if tag in self._tag_index:
                self._tag_index[tag] = [
                    tid for tid in self._tag_index[tag]
                    if tid != trajectory_id
                ]
        
        if trajectory.agent_id in self._agent_index:
            self._agent_index[trajectory.agent_id] = [
                tid for tid in self._agent_index[trajectory.agent_id]
                if tid != trajectory_id
            ]
        
        if trajectory.task_id in self._task_index:
            self._task_index[trajectory.task_id] = [
                tid for tid in self._task_index[trajectory.task_id]
                if tid != trajectory_id
            ]
        
        # Delete from database
        if self._conn:
            self._conn.execute(
                "DELETE FROM trajectories WHERE id = ?",
                (trajectory_id,)
            )
            self._conn.execute(
                "DELETE FROM trajectory_tags WHERE trajectory_id = ?",
                (trajectory_id,)
            )
            self._conn.commit()
        
        self._metrics.total_trajectories -= 1
        
        return True
    
    # ===== Search Operations =====
    
    async def search_by_tag(self, tag: str, limit: int = 10) -> List[ReasoningTrajectory]:
        """
        Search trajectories by tag.
        
        Args:
            tag: Tag to search for
            limit: Maximum results
            
        Returns:
            List of matching trajectories
        """
        self._check_initialized()
        
        trajectory_ids = self._tag_index.get(tag, [])
        trajectories = [
            self._trajectories[tid]
            for tid in trajectory_ids[:limit]
            if tid in self._trajectories
        ]
        
        return trajectories
    
    async def search_by_agent(
        self,
        agent_id: str,
        success_only: bool = False,
        limit: int = 10
    ) -> List[ReasoningTrajectory]:
        """
        Search trajectories by agent.
        
        Args:
            agent_id: Agent ID
            success_only: Only return successful trajectories
            limit: Maximum results
            
        Returns:
            List of matching trajectories
        """
        self._check_initialized()
        
        trajectory_ids = self._agent_index.get(agent_id, [])
        trajectories = [
            self._trajectories[tid]
            for tid in trajectory_ids
            if tid in self._trajectories
        ]
        
        if success_only:
            trajectories = [t for t in trajectories if t.success]
        
        return trajectories[:limit]
    
    async def search_similar(
        self,
        query_embedding: NDArray,
        k: int = 5,
        threshold: Optional[float] = None,
        success_only: bool = False
    ) -> List[TrajectorySearchResult]:
        """
        Search for similar trajectories using embedding.
        
        Args:
            query_embedding: Query embedding vector
            k: Number of results
            threshold: Minimum similarity threshold
            success_only: Only return successful trajectories
            
        Returns:
            List of search results with similarity scores
        """
        self._check_initialized()
        
        results: List[TrajectorySearchResult] = []
        
        for tid, embedding in self._embedding_index.items():
            if embedding is None:
                continue
            
            trajectory = self._trajectories.get(tid)
            if not trajectory:
                continue
            
            if success_only and not trajectory.success:
                continue
            
            similarity = calculate_similarity(query_embedding, embedding)
            
            if threshold is not None and similarity < threshold:
                continue
            
            results.append(TrajectorySearchResult(
                trajectory=trajectory,
                score=similarity
            ))
        
        # Sort by score (descending)
        results.sort(key=lambda r: r.score, reverse=True)
        
        return results[:k]
    
    async def search_by_task(self, task_id: str) -> List[ReasoningTrajectory]:
        """
        Get all trajectories for a task.
        
        Args:
            task_id: Task ID
            
        Returns:
            List of trajectories
        """
        self._check_initialized()
        
        trajectory_ids = self._task_index.get(task_id, [])
        return [
            self._trajectories[tid]
            for tid in trajectory_ids
            if tid in self._trajectories
        ]
    
    # ===== Utility Methods =====
    
    async def get_successful_patterns(
        self,
        min_frequency: int = 2,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Extract successful patterns from trajectories.
        
        Args:
            min_frequency: Minimum frequency for a pattern
            limit: Maximum patterns to return
            
        Returns:
            List of patterns with frequencies
        """
        self._check_initialized()
        
        # Group by final result
        patterns: Dict[str, int] = {}
        
        for trajectory in self._trajectories.values():
            if not trajectory.success:
                continue
            
            key = trajectory.final_result[:100]  # Truncate for grouping
            patterns[key] = patterns.get(key, 0) + 1
        
        # Filter by frequency
        patterns = {k: v for k, v in patterns.items() if v >= min_frequency}
        
        # Sort by frequency
        sorted_patterns = sorted(
            patterns.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        return [
            {"pattern": k, "frequency": v}
            for k, v in sorted_patterns[:limit]
        ]
    
    async def get_statistics(self) -> Dict[str, Any]:
        """Get bank statistics"""
        self._check_initialized()
        
        total = len(self._trajectories)
        successful = sum(1 for t in self._trajectories.values() if t.success)
        failed = total - successful
        
        avg_steps = 0.0
        avg_time = 0.0
        if total > 0:
            avg_steps = sum(t.total_steps for t in self._trajectories.values()) / total
            avg_time = sum(t.total_time_ms for t in self._trajectories.values()) / total
        
        return {
            "total_trajectories": total,
            "successful": successful,
            "failed": failed,
            "success_rate": successful / total if total > 0 else 0,
            "average_steps": avg_steps,
            "average_time_ms": avg_time,
            "unique_tags": len(self._tag_index),
            "unique_agents": len(self._agent_index),
            "unique_tasks": len(self._task_index),
        }
    
    async def clear(self) -> int:
        """
        Clear all trajectories.
        
        Returns:
            Number of trajectories cleared
        """
        self._check_initialized()
        
        count = len(self._trajectories)
        
        self._trajectories.clear()
        self._embedding_index.clear()
        self._tag_index.clear()
        self._agent_index.clear()
        self._task_index.clear()
        
        if self._conn:
            self._conn.execute("DELETE FROM trajectories")
            self._conn.execute("DELETE FROM trajectory_tags")
            self._conn.commit()
        
        self._metrics.total_trajectories = 0
        
        return count
    
    async def _maybe_compress(self) -> None:
        """Compress trajectories if over limit"""
        if len(self._trajectories) <= self.config.max_trajectories:
            return
        
        # Sort by created_at (oldest first)
        sorted_trajectories = sorted(
            self._trajectories.values(),
            key=lambda t: t.created_at
        )
        
        # Remove oldest trajectories
        to_remove = len(sorted_trajectories) - int(
            self.config.max_trajectories * self.config.compression_ratio
        )
        
        for trajectory in sorted_trajectories[:to_remove]:
            await self.delete(trajectory.id)
    
    def _check_initialized(self) -> None:
        """Check if bank is initialized"""
        if not self._initialized:
            raise RuntimeError("ReasoningBank not initialized. Call initialize() first.")


# ===== Factory Functions =====

def create_reasoning_bank() -> ReasoningBank:
    """Create a default ReasoningBank"""
    return ReasoningBank(ReasoningBankConfig())


def create_compressed_bank(max_trajectories: int = 5000) -> ReasoningBank:
    """Create a compressed ReasoningBank"""
    return ReasoningBank(ReasoningBankConfig(
        max_trajectories=max_trajectories,
        enable_compression=True,
        compression_ratio=0.5
    ))
