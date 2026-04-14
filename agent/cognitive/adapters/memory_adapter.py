"""
Memory Adapter - 将Cognitive Core的HNSW向量搜索与Kunming现有MemoryManager整合
消除重复：Kunming有FTS5文本搜索，Cognitive Core有HNSW向量搜索，合并为混合搜索
"""

import asyncio
import json
import logging
import sqlite3
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path

from kunming_constants import get_kunming_home
from agent.memory_provider import MemoryProvider

logger = logging.getLogger(__name__)


@dataclass
class HybridSearchResult:
    """混合搜索结果"""
    id: str
    content: str
    memory_type: str
    fts_score: float
    vector_score: float
    hybrid_score: float
    metadata: Dict[str, Any]


class HybridMemoryProvider(MemoryProvider):
    """
    混合内存提供者 - 结合Kunming的FTS5和Cognitive Core的HNSW
    
    这是消除重复实现的核心适配器：
    - Kunming原有：FTS5文本搜索（关键词匹配）
    - Cognitive Core新增：HNSW向量搜索（语义相似度）
    - 合并后：混合搜索（结合两者优势）
    """
    
    def __init__(self):
        self._fts_db_path = get_kunming_home() / "memories" / "memory.db"
        self._vector_index = None
        self._initialized = False
        self._session_id = ""
        self._last_prefetch_result = ""

    @property
    def name(self) -> str:
        return "hybrid"

    def is_available(self) -> bool:
        return True

    def initialize(self, session_id: str = "", **kwargs) -> None:
        self._session_id = session_id
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    pool.submit(lambda: asyncio.run(self._async_initialize())).result()
            else:
                asyncio.run(self._async_initialize())
        except RuntimeError:
            asyncio.run(self._async_initialize())

    async def _async_initialize(self) -> None:
        if self._initialized:
            return
        try:
            from plugins.memory.hnsw_local import MemoryStore, MemoryStoreConfig
            config = MemoryStoreConfig(
                dimensions=1536,
                auto_embed=True,
                persistence_enabled=True
            )
            self._vector_index = MemoryStore(config=config)
            await self._vector_index.initialize()
            self._initialized = True
        except ImportError as e:
            logger.warning(f"HNSW plugin not available: {e}")
            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize HybridMemoryProvider: {e}")
            raise

    def system_prompt_block(self) -> str:
        if not self._initialized:
            return ""
        parts = ["[Hybrid Memory Provider active - FTS5 + HNSW vector search]"]
        if self._vector_index:
            parts.append("Vector search: enabled")
        else:
            parts.append("Vector search: unavailable (FTS5 only)")
        return "\n".join(parts)

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        return self._last_prefetch_result

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        try:
            if not self._initialized:
                return
            loop = asyncio.get_running_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(lambda: asyncio.run(self._do_prefetch(query)))
                    self._last_prefetch_result = future.result()
            else:
                self._last_prefetch_result = asyncio.run(self._do_prefetch(query))
        except RuntimeError:
            self._last_prefetch_result = asyncio.run(self._do_prefetch(query))
        except Exception as e:
            logger.debug(f"Prefetch failed: {e}")

    async def _do_prefetch(self, query: str) -> str:
        results = await self.search(query, k=5, use_hybrid=True)
        if not results:
            return ""
        lines = []
        for r in results[:3]:
            lines.append(f"- {r.content[:200]}")
        return "\n".join(lines)

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "") -> None:
        pass

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return []

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        pass
    
    async def search(
        self,
        query: str,
        k: int = 10,
        use_hybrid: bool = True
    ) -> List[HybridSearchResult]:
        """
        混合搜索 - 同时利用FTS5和HNSW
        
        Args:
            query: 搜索查询
            k: 返回结果数量
            use_hybrid: 是否使用混合评分
        
        Returns:
            按相关性排序的混合结果
        """
        # 1. FTS5文本搜索（在后台线程执行）
        fts_results = await asyncio.to_thread(self._fts_search_sync, query, k * 2)
        
        # 2. HNSW向量搜索
        vector_results = []
        if self._vector_index:
            vector_results = await self._vector_search(query, k * 2)
        
        # 3. 混合评分
        if use_hybrid and vector_results:
            return self._merge_and_rank(fts_results, vector_results, k)
        
        # 否则只返回向量搜索结果（语义更准）
        if vector_results:
            return vector_results[:k]
        
        # 如果没有向量结果，返回FTS结果转换后的格式
        return [
            HybridSearchResult(
                id=r['id'],
                content=r['content'],
                memory_type=r.get('type', 'unknown'),
                fts_score=r.get('score', 0.0),
                vector_score=0.0,
                hybrid_score=r.get('score', 0.0) * 0.3,
                metadata={}
            )
            for r in fts_results[:k]
        ]
    
    def _fts_search_sync(
        self,
        query: str,
        k: int
    ) -> List[Dict[str, Any]]:
        """同步执行FTS5搜索（用于asyncio.to_thread）"""
        results = []
        
        try:
            conn = sqlite3.connect(str(self._fts_db_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='memory_fts_idx'
            """)
            
            if cursor.fetchone():
                cursor.execute("""
                    SELECT fts.id, fts.content, fts.memory_type,
                           rank as score
                    FROM memory_fts_idx fts
                    WHERE fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                """, (query, k))
                
                for row in cursor.fetchall():
                    results.append({
                        'id': str(row[0]),
                        'content': row[1],
                        'type': row[2],
                        'score': float(row[3]) if row[3] else 0.0,
                        'source': 'fts'
                    })
            
            conn.close()
        except Exception as e:
            logger.debug(f"FTS5 search failed: {e}")
        
        return results
    
    async def _vector_search(
        self,
        query: str,
        k: int
    ) -> List[HybridSearchResult]:
        """使用HNSW向量搜索"""
        if not self._vector_index:
            return []
        
        try:
            # 使用迁移后的插件接口
            from plugins.memory.hnsw_local import SearchOptions
            
            search_options = SearchOptions(k=k)
            search_results = await self._vector_index.search(query, search_options)
            
            return [
                HybridSearchResult(
                    id=r.entry.id,
                    content=r.entry.content,
                    memory_type=r.entry.type.value if hasattr(r.entry, 'type') else 'unknown',
                    fts_score=0.0,
                    vector_score=r.score,
                    hybrid_score=r.score,
                    metadata=r.entry.metadata
                )
                for r in search_results
            ]
        except Exception as e:
            logger.warning(f"Vector search failed: {e}")
            return []
    
    def _merge_and_rank(
        self,
        fts_results: List[Dict[str, Any]],
        vector_results: List[HybridSearchResult],
        k: int
    ) -> List[HybridSearchResult]:
        """合并并重新排序FTS和向量搜索结果"""
        
        # 创建ID到结果的映射
        fts_map = {r['id']: r for r in fts_results}
        vector_map = {r.id: r for r in vector_results}
        
        # 所有唯一ID
        all_ids = set(fts_map.keys()) | set(vector_map.keys())
        
        merged = []
        for id in all_ids:
            fts_score = fts_map.get(id, {}).get('score', 0.0)
            vector_result = vector_map.get(id)
            
            if vector_result:
                # 同时有两者 - 加权混合
                hybrid_score = 0.3 * fts_score + 0.7 * vector_result.vector_score
                merged.append(HybridSearchResult(
                    id=id,
                    content=vector_result.content,
                    memory_type=vector_result.memory_type,
                    fts_score=fts_score,
                    vector_score=vector_result.vector_score,
                    hybrid_score=hybrid_score,
                    metadata=vector_result.metadata
                ))
            else:
                # 只有FTS结果
                content = fts_map[id].get('content', '')
                merged.append(HybridSearchResult(
                    id=id,
                    content=content,
                    memory_type=fts_map[id].get('type', 'unknown'),
                    fts_score=fts_score,
                    vector_score=0.0,
                    hybrid_score=fts_score * 0.3,  # 降低权重
                    metadata={}
                ))
        
        # 按混合分数排序
        merged.sort(key=lambda x: x.hybrid_score, reverse=True)
        
        return merged[:k]
    
    async def store(
        self,
        content: str,
        memory_type: str = "episodic",
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        存储记忆 - 同时存入FTS5和HNSW
        
        消除重复：一次存储，两个系统都可用
        使用事务机制确保数据一致性
        """
        if not self._initialized:
            raise RuntimeError("HybridMemoryProvider not initialized. Call initialize() first.")
        
        memory_id = f"memory_{hashlib.sha256(content.encode()).hexdigest()[:16]}"
        hnsw_success = False
        fts_success = False
        
        try:
            # 存入HNSW索引
            if self._vector_index:
                try:
                    from plugins.memory.hnsw_local import MemoryEntryInput, MemoryType
                    
                    input_data = MemoryEntryInput(
                        key=memory_id,
                        content=content,
                        type=MemoryType(memory_type),
                        metadata=metadata or {}
                    )
                    entry = await self._vector_index.store(input_data)
                    hnsw_success = True
                except Exception as e:
                    logger.warning(f"HNSW store failed: {e}")
            
            # 存入FTS5索引（Kunming原生）- 使用后台线程
            try:
                await asyncio.to_thread(
                    self._fts_store_sync,
                    memory_id,
                    content,
                    memory_type,
                    metadata
                )
                fts_success = True
            except Exception as e:
                logger.warning(f"FTS5 store failed: {e}")
            
            # 检查存储结果
            if not hnsw_success and not fts_success:
                raise RuntimeError("Failed to store memory in both HNSW and FTS5")
            
            if hnsw_success != fts_success:
                logger.warning(
                    f"Partial memory storage: HNSW={hnsw_success}, FTS5={fts_success}. "
                    f"Data consistency may be compromised."
                )
            
            return memory_id
            
        except Exception as e:
            logger.error(f"Memory store failed: {e}")
            # 如果HNSW成功但FTS5失败，尝试回滚HNSW
            if hnsw_success and self._vector_index:
                try:
                    await self._vector_index.delete(memory_id)
                    logger.info(f"Rolled back HNSW entry {memory_id}")
                except Exception as rollback_error:
                    logger.error(f"Failed to rollback HNSW entry: {rollback_error}")
            raise
    
    def _fts_store_sync(
        self,
        memory_id: str,
        content: str,
        memory_type: str,
        metadata: Optional[Dict[str, Any]]
    ) -> None:
        """同步存储到FTS5（用于asyncio.to_thread）"""
        try:
            self._fts_db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(str(self._fts_db_path)) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS memory_fts (
                        id TEXT PRIMARY KEY,
                        content TEXT,
                        memory_type TEXT,
                        metadata TEXT,
                        timestamp TEXT DEFAULT (datetime('now'))
                    )
                """)
                conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts_idx
                    USING fts5(id, content, memory_type, tokenize='trigram')
                """)
                meta_json = json.dumps(metadata) if metadata else "{}"
                conn.execute(
                    "INSERT OR REPLACE INTO memory_fts (id, content, memory_type, metadata) VALUES (?, ?, ?, ?)",
                    (memory_id, content, memory_type, meta_json),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO memory_fts_idx (id, content, memory_type) VALUES (?, ?, ?)",
                    (memory_id, content, memory_type),
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"FTS5 store sync failed: {e}")
            raise


def get_hybrid_memory_provider() -> HybridMemoryProvider:
    """创建新的混合内存提供者实例（每次调用重新解析profile路径）"""
    return HybridMemoryProvider()
