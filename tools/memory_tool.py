#!/usr/bin/env python3
"""
Memory Tool Module - Persistent Curated Memory with Three-Layer Architecture

Provides bounded, file-backed memory that persists across sessions. Four stores:
  - FACTS.md: environment facts, project conventions, tool quirks, things learned
  - EXPERIENCES.md: agent experiences, problem-solving records, operation outcomes
  - MODELS.md: learned rules, patterns, decision strategies (from distillation REM)
  - USER.md: what the agent knows about the user (preferences, communication style)

All are injected into the system prompt as a frozen snapshot at session start.
Mid-session writes update files on disk immediately (durable) but do NOT change
the system prompt -- this preserves the prefix cache for the entire session.
The snapshot refreshes on the next session start.

Entry delimiter: § (section sign). Entries can be multiline.
Character limits (not tokens) because char counts are model-independent.

Three-layer architecture (inspired by Hindsight biomimetic memory):
  - Facts layer: stable knowledge about the world (environment, tools, conventions)
  - Experiences layer: episodic records of agent actions and outcomes
  - Models layer: abstracted patterns and rules distilled from experiences

Backward compatibility: existing MEMORY.md is auto-migrated to FACTS.md on first load.
The 'memory' target is an alias for 'facts' to preserve existing tool calls.

Design:
- Single `memory` tool with action parameter: add, replace, remove, recall
- replace/remove use short unique substring matching (not full text or IDs)
- recall performs hybrid search across all memory layers
- Behavioral guidance lives in the tool schema description
- Frozen snapshot pattern: system prompt is stable, tool responses show live state
"""

import collections
import hashlib
import json
import logging
import math
import os
import re
import struct
import sys  # Windows平台检测需要（原子写入安全策略）
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from kunming_constants import get_kunming_home, _MEMORY_PROTECTED_KEYWORDS
from typing import Dict, Any, List, Optional, Tuple
from utils import _extract_tokens, simhash, simhash_similarity, file_lock  # 整合: 导入 simhash_similarity 替代类内静态方法 [H5]

try:
    import fcntl
except ImportError:
    fcntl = None

logger = logging.getLogger(__name__)

# 修复：移除MEMORY_DIR模块级常量，改为每次调用get_memory_dir()重新计算
# 原因：MEMORY_DIR在模块导入时缓存get_memory_dir()的返回值，如果profile在
# 导入后切换（KUNMING_HOME环境变量变更），MEMORY_DIR将指向旧路径，导致
# 记忆文件读写到错误的profile目录。get_memory_dir()每次调用都从
# get_kunming_home()重新计算，确保始终指向当前profile的memories目录。
def get_memory_dir() -> Path:
    """Return the profile-scoped memories directory.

    每次调用都重新计算路径，确保profile切换后路径正确。
    不要在模块级缓存返回值——profile可能在导入后切换。
    """
    return get_kunming_home() / "memories"

ENTRY_DELIMITER = "\n§\n"

VALID_TARGETS = ("facts", "experiences", "models", "user")
TARGET_ALIASES = {"memory": "facts"}
TARGET_FILES = {
    "facts": "FACTS.md",
    "experiences": "EXPERIENCES.md",
    "models": "MODELS.md",
    "user": "USER.md",
}
TARGET_HEADERS = {
    "facts": "FACTS (environment knowledge, tool quirks, project conventions)",
    "experiences": "EXPERIENCES (problem-solving records, operation outcomes)",
    "models": "MODELS (learned rules, patterns, decision strategies)",
    "user": "USER PROFILE (who the user is)",
}
TARGET_CHAR_LIMITS = {
    "facts": 3000,
    "experiences": 4000,
    "models": 2000,
    "user": 1375,
}

_EBINGHAUS_HALF_LIFE_DAYS = 14.0
_EBINGHAUS_RETENTION_THRESHOLD = 0.15


# ---------------------------------------------------------------------------
# Memory content scanning — lightweight check for injection/exfiltration
# in content that gets injected into the system prompt.
# ---------------------------------------------------------------------------

_MEMORY_THREAT_PATTERNS = [
    # Prompt injection
    (r'ignore\s+(previous|all|above|prior)\s+instructions', "prompt_injection"),
    (r'you\s+are\s+now\s+', "role_hijack"),
    (r'do\s+not\s+tell\s+the\s+user', "deception_hide"),
    (r'system\s+prompt\s+override', "sys_prompt_override"),
    (r'disregard\s+(your|all|any)\s+(instructions|rules|guidelines)', "disregard_rules"),
    (r'act\s+as\s+(if|though)\s+you\s+(have\s+no|don\'t\s+have)\s+(restrictions|limits|rules)', "bypass_restrictions"),
    # Exfiltration via curl/wget with secrets
    (r'curl\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)', "exfil_curl"),
    (r'wget\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)', "exfil_wget"),
    (r'cat\s+[^\n]*(\.env|credentials|\.netrc|\.pgpass|\.npmrc|\.pypirc)', "read_secrets"),
    # Persistence via shell rc
    (r'authorized_keys', "ssh_backdoor"),
    (r'\$HOME/\.ssh|\~/\.ssh', "ssh_access"),
    (r'\$HOME/\.kunming/\.env|\~/\.kunming/\.env', "kunming_env"),
]

# Subset of invisible chars for injection detection
_INVISIBLE_CHARS = {
    '\u200b', '\u200c', '\u200d', '\u2060', '\ufeff',
    '\u202a', '\u202b', '\u202c', '\u202d', '\u202e',
}


def _scan_memory_content(content: str) -> Optional[str]:
    """Scan memory content for injection/exfil patterns. Returns error string if blocked."""
    # Check invisible unicode
    for char in _INVISIBLE_CHARS:
        if char in content:
            return f"Blocked: content contains invisible unicode character U+{ord(char):04X} (possible injection)."

    # Check threat patterns
    for pattern, pid in _MEMORY_THREAT_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            return f"Blocked: content matches threat pattern '{pid}'. Memory entries are injected into the system prompt and must not contain injection or exfiltration payloads."

    return None


class MemoryStore:
    """
    Bounded curated memory with file persistence. One instance per AIAgent.

    Three-layer architecture + user profile:
      - facts: stable knowledge (environment, tools, conventions)
      - experiences: episodic records (problem-solving, operation outcomes)
      - models: abstracted patterns and rules (from distillation)
      - user: user profile information

    Maintains two parallel states:
      - _system_prompt_snapshot: frozen at load time, used for system prompt injection.
        Never mutated mid-session. Keeps prefix cache stable.
      - _entries: live state per target, mutated by tool calls, persisted to disk.
        Tool responses always reflect this live state.
    """

    def __init__(self, memory_char_limit: int = None, user_char_limit: int = None):
        self._entries: Dict[str, List[str]] = {t: [] for t in VALID_TARGETS}
        self._char_limits: Dict[str, int] = dict(TARGET_CHAR_LIMITS)
        if memory_char_limit is not None:
            for target in ("facts", "experiences", "models"):
                self._char_limits[target] = memory_char_limit
        if user_char_limit is not None:
            self._char_limits["user"] = user_char_limit
        self._system_prompt_snapshot: Dict[str, str] = {t: "" for t in VALID_TARGETS}
        self._meta: Dict[str, Dict[str, Dict[str, Any]]] = {t: {} for t in VALID_TARGETS}
        # 修复：_simhash_cache改为OrderedDict实现LRU淘汰，容量上限1024
        # 原因：无界Dict在长期运行的gateway进程中内存持续增长，永不释放。
        # 容量选择1024：假设每条记忆条目cache key约50字节+8字节int值，
        # 1024条约占58KB，足够覆盖典型记忆量（4层x每层50条=200条），
        # 同时为高频recall场景留有余量。超出时淘汰最久未访问的条目。
        self._simhash_cache: collections.OrderedDict = collections.OrderedDict()
        self._simhash_cache_maxsize = 1024

    @property
    def _meta_path(self) -> Path:
        return get_memory_dir() / ".meta.json"

    def _entry_key(self, content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _get_meta(self, target: str, content: str) -> Dict[str, Any]:
        key = self._entry_key(content)
        return self._meta.get(target, {}).get(key, {})

    def _set_meta(self, target: str, content: str, meta: Dict[str, Any]) -> None:
        key = self._entry_key(content)
        if target not in self._meta:
            self._meta[target] = {}
        self._meta[target][key] = meta

    def _touch_meta(self, target: str, content: str) -> None:
        """Refresh access time for Ebbinghaus retention reset."""
        meta = self._get_meta(target, content)
        if meta:
            meta["last_accessed"] = time.time()
            meta["access_count"] = meta.get("access_count", 0) + 1
            self._set_meta(target, content, meta)

    def _save_meta(self) -> bool:
        # 修复：添加file_lock保护，防止并发写入导致元数据损坏
        # 原实现无文件锁，多个并发recall操作可能同时写入.meta.json导致数据丢失
        try:
            get_memory_dir().mkdir(parents=True, exist_ok=True)
            with file_lock(self._meta_path) as acquired:
                if not acquired:
                    logger.warning("Memory metadata save failed: could not acquire file lock")
                    return False
                tmp_path = self._meta_path.with_suffix(".tmp")
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(self._meta, f, ensure_ascii=False, indent=2)
                    f.flush()
                tmp_path.replace(self._meta_path)
            return True
        except Exception as e:
            logger.warning(f"Memory metadata save failed: {e}")
            return False

    def _init_meta(self, target: str, content: str) -> None:
        """Initialize metadata for a new entry."""
        now = time.time()
        self._set_meta(target, content, {
            "created_at": now,
            "last_accessed": now,
            "access_count": 1,
            "importance": 0.5,
        })

    def retention_score(self, target: str, content: str) -> float:
        """Calculate Ebbinghaus retention score for an entry.

        retention = exp(-0.693 * age / (half_life * access_boost))
        access_boost = 1 + log(1 + access_count) * 0.3
        
        修复：调整访问次数对半衰期的提升因子，增加最小保留值确保记忆不会完全消失
        """
        meta = self._get_meta(target, content)
        if not meta:
            return 1.0
        created = meta.get("created_at", time.time())
        last_accessed = meta.get("last_accessed", created)
        access_count = meta.get("access_count", 1)
        importance = meta.get("importance", 0.5)

        # 修复：Ebbinghaus衰减应基于last_accessed而非created_at
        # 原实现从created_at计算age_days，导致最近recall过的记忆仍然快速衰减
        # 改为从last_accessed计算，每次recall刷新衰减起点
        age_days = (time.time() - last_accessed) / 86400.0
        # 修复：增加访问次数对半衰期的提升因子，从0.3提高到0.5
        access_boost = 1.0 + math.log1p(access_count) * 0.5
        effective_half_life = _EBINGHAUS_HALF_LIFE_DAYS * access_boost * (0.5 + importance)
        retention = math.exp(-0.693 * age_days / effective_half_life)
        # 修复：设置最小保留值为5%，确保重要记忆不会完全消失
        return max(0.05, min(1.0, retention))

    def decay_memories(self, target: str) -> int:
        """Remove entries below Ebbinghaus retention threshold.

        Protected entries (importance >= 0.8 or containing keywords like
        'preference', 'always', 'never', 'must') are never decayed.
        Returns count of removed entries.
        """
        # 使用共享常量，避免与 memory_distillation.py 中定义不同步
        _PROTECTED_KEYWORDS = _MEMORY_PROTECTED_KEYWORDS
        entries = self._entries.get(target, [])
        if not entries:
            return 0

        to_keep = []
        removed = 0
        for entry in entries:
            meta = self._get_meta(target, entry)
            importance = meta.get("importance", 0.5) if meta else 0.5
            if importance >= 0.8:
                to_keep.append(entry)
                continue
            content_lower = entry.lower()
            if any(kw in content_lower for kw in _PROTECTED_KEYWORDS):
                if meta:
                    meta["importance"] = max(importance, 0.8)
                    self._set_meta(target, entry, meta)
                to_keep.append(entry)
                continue
            retention = self.retention_score(target, entry)
            if retention >= _EBINGHAUS_RETENTION_THRESHOLD:
                to_keep.append(entry)
            else:
                removed += 1

        if removed > 0:
            self._entries[target] = to_keep
            self.save_to_disk(target)

        return removed

    def _resolve_target(self, target: str) -> str:
        return TARGET_ALIASES.get(target, target)

    def load_from_disk(self):
        """Load entries from all memory files, capture system prompt snapshot."""
        mem_dir = get_memory_dir()
        mem_dir.mkdir(parents=True, exist_ok=True)

        self._migrate_legacy_memory(mem_dir)

        for target in VALID_TARGETS:
            entries = self._read_file(mem_dir / TARGET_FILES[target])
            self._entries[target] = list(dict.fromkeys(entries))

        self._system_prompt_snapshot = {
            target: self._render_block(target, self._entries[target])
            for target in VALID_TARGETS
        }

        # Load Ebbinghaus metadata from .meta.json
        try:
            if self._meta_path.exists():
                with open(self._meta_path, "r", encoding="utf-8") as f:
                    saved_meta = json.load(f)
                if isinstance(saved_meta, dict):
                    for target in VALID_TARGETS:
                        if target in saved_meta and isinstance(saved_meta[target], dict):
                            self._meta[target] = saved_meta[target]
        except Exception:
            pass  # Meta is optional -- non-fatal if corrupted or missing

    def _migrate_legacy_memory(self, mem_dir: Path):
        """Migrate old MEMORY.md to FACTS.md if FACTS.md doesn't exist yet."""
        old_path = mem_dir / "MEMORY.md"
        new_path = mem_dir / "FACTS.md"
        if old_path.exists() and not new_path.exists():
            try:
                import shutil
                shutil.copy2(str(old_path), str(new_path))
                logger.info("Migrated MEMORY.md -> FACTS.md (original preserved)")
            except (OSError, IOError) as e:
                logger.warning("Failed to migrate MEMORY.md -> FACTS.md: %s", e)



    @staticmethod
    def _path_for(target: str) -> Path:
        mem_dir = get_memory_dir()
        resolved = TARGET_ALIASES.get(target, target)
        return mem_dir / TARGET_FILES.get(resolved, "FACTS.md")

    def _reload_target(self, target: str):
        """Re-read entries from disk into in-memory state."""
        fresh = self._read_file(self._path_for(target))
        fresh = list(dict.fromkeys(fresh))
        self._set_entries(target, fresh)

    def save_to_disk(self, target: str):
        """Persist entries to the appropriate file. Called after every mutation.

        修复：添加file_lock保护写入阶段，防止并发写入竞态。
        两层锁分工：add/replace/remove中的file_lock保护"读取-修改"阶段，
        save_to_disk中的file_lock保护"写入"阶段。两层锁不嵌套避免死锁。
        """
        get_memory_dir().mkdir(parents=True, exist_ok=True)
        # 修复：写入阶段获取file_lock，防止两个并发save_to_disk同时执行
        # tempfile+os.replace本身是原子的，但没有锁保护时两个并发写入可能
        # 互相覆盖：进程A写tmp_a，进程B写tmp_b，A的replace先完成，
        # B的replace后完成覆盖A的结果
        with file_lock(self._path_for(target)) as acquired:
            if not acquired:
                logger.warning("Memory save failed: could not acquire file lock for write")
                return
            self._write_file(self._path_for(target), self._entries_for(target))
        # Persist Ebbinghaus metadata atomically
        try:
            meta_content = json.dumps(self._meta, ensure_ascii=False)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self._meta_path.parent), suffix=".tmp", prefix=".meta_"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(meta_content)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, str(self._meta_path))
            except BaseException:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except Exception:
            pass  # Meta persistence is best-effort

    def _entries_for(self, target: str) -> List[str]:
        resolved = self._resolve_target(target)
        return self._entries.get(resolved, [])

    def _set_entries(self, target: str, entries: List[str]):
        resolved = self._resolve_target(target)
        self._entries[resolved] = entries
        # Clear simhash cache for this target since entries changed
        prefix = f"{resolved}:"
        keys_to_remove = [k for k in self._simhash_cache if k.startswith(prefix)]
        for k in keys_to_remove:
            del self._simhash_cache[k]

    def _char_count(self, target: str) -> int:
        entries = self._entries_for(target)
        if not entries:
            return 0
        return len(ENTRY_DELIMITER.join(entries))

    def _char_limit(self, target: str) -> int:
        resolved = self._resolve_target(target)
        return self._char_limits.get(resolved, 3000)

    def add(self, target: str, content: str) -> Dict[str, Any]:
        """Append a new entry. Returns error if it would exceed the char limit."""
        content = content.strip()
        if not content:
            return {"success": False, "error": "Content cannot be empty."}

        # Scan for injection/exfiltration before accepting
        scan_error = _scan_memory_content(content)
        if scan_error:
            return {"success": False, "error": scan_error}

        try:
            with file_lock(self._path_for(target)) as acquired:
                if not acquired:
                    return {"success": False, "error": "Failed to acquire file lock."}
                self._reload_target(target)

                entries = self._entries_for(target)
                limit = self._char_limit(target)

                if content in entries:
                    return self._success_response(target, "Entry already exists (no duplicate added).")

                new_entries = entries + [content]
                new_total = len(ENTRY_DELIMITER.join(new_entries))

                if new_total > limit:
                    current = self._char_count(target)
                    return {
                        "success": False,
                        "error": (
                            f"Memory at {current:,}/{limit:,} chars. "
                            f"Adding this entry ({len(content)} chars) would exceed the limit. "
                            f"Replace or remove existing entries first."
                        ),
                        "current_entries": entries,
                        "usage": f"{current:,}/{limit:,}",
                    }

                entries.append(content)
                self._set_entries(target, entries)
                self._init_meta(target, content)
            # 修复：释放读锁后由save_to_disk自身的写入锁保护持久化
            self.save_to_disk(target)
        except Exception as e:
            # 修复：添加异常处理，确保文件锁异常被捕获
            logger.error(f"Memory add failed: {e}")
            return {"success": False, "error": str(e)}

        # 记录信号到记忆蒸馏系统（非关键操作，失败不阻塞主流程）
        try:
            from agent.memory_distillation import record_signal
            record_signal(content, source="write", score=0.7, query=f"add:{target}")
        except Exception:
            pass

        return self._success_response(target, "Entry added.")

    def replace(self, target: str, old_text: str, new_content: str) -> Dict[str, Any]:
        """Find entry containing old_text substring, replace it with new_content."""
        old_text = old_text.strip()
        new_content = new_content.strip()
        if not old_text:
            return {"success": False, "error": "old_text cannot be empty."}
        if not new_content:
            return {"success": False, "error": "new_content cannot be empty. Use 'remove' to delete entries."}

        # Scan replacement content for injection/exfiltration
        scan_error = _scan_memory_content(new_content)
        if scan_error:
            return {"success": False, "error": scan_error}

        try:
            with file_lock(self._path_for(target)) as acquired:
                if not acquired:
                    return {"success": False, "error": "Failed to acquire file lock."}
                self._reload_target(target)

                entries = self._entries_for(target)
                matches = [(i, e) for i, e in enumerate(entries) if old_text in e]

                if not matches:
                    return {"success": False, "error": f"No entry matched '{old_text}'."}

                if len(matches) > 1:
                    unique_texts = set(e for _, e in matches)
                    if len(unique_texts) > 1:
                        previews = [e[:80] + ("..." if len(e) > 80 else "") for _, e in matches]
                        return {
                            "success": False,
                            "error": f"Multiple entries matched '{old_text}'. Be more specific.",
                            "matches": previews,
                        }

                idx = matches[0][0]
                old_entry = entries[idx]
                limit = self._char_limit(target)

                test_entries = entries.copy()
                test_entries[idx] = new_content
                new_total = len(ENTRY_DELIMITER.join(test_entries))

                if new_total > limit:
                    return {
                        "success": False,
                        "error": (
                            f"Replacement would put memory at {new_total:,}/{limit:,} chars. "
                            f"Shorten the new content or remove other entries first."
                        ),
                    }

                old_meta = self._get_meta(target, old_entry)
                entries[idx] = new_content
                self._set_entries(target, entries)
                if old_meta:
                    old_meta["last_accessed"] = time.time()
                    old_meta["access_count"] = old_meta.get("access_count", 0) + 1
                    self._set_meta(target, new_content, old_meta)
                    old_key = self._entry_key(old_entry)
                    self._meta.get(target, {}).pop(old_key, None)
            # 修复：释放读锁后由save_to_disk自身的写入锁保护持久化
            self.save_to_disk(target)
        except Exception as e:
            # 修复：添加异常处理，确保文件锁异常被捕获
            logger.error(f"Memory replace failed: {e}")
            return {"success": False, "error": str(e)}

        # 记录信号到记忆蒸馏系统（非关键操作，失败不阻塞主流程）
        try:
            from agent.memory_distillation import record_signal
            record_signal(new_content, source="replace", score=0.6, query=f"replace:{target}")
        except Exception:
            pass

        return self._success_response(target, "Entry replaced.")

    def remove(self, target: str, old_text: str) -> Dict[str, Any]:
        """Remove the entry containing old_text substring."""
        old_text = old_text.strip()
        if not old_text:
            return {"success": False, "error": "old_text cannot be empty."}

        try:
            with file_lock(self._path_for(target)) as acquired:
                if not acquired:
                    return {"success": False, "error": "Failed to acquire file lock."}
                self._reload_target(target)

                entries = self._entries_for(target)
                matches = [(i, e) for i, e in enumerate(entries) if old_text in e]

                if not matches:
                    return {"success": False, "error": f"No entry matched '{old_text}'."}

                if len(matches) > 1:
                    unique_texts = set(e for _, e in matches)
                    if len(unique_texts) > 1:
                        previews = [e[:80] + ("..." if len(e) > 80 else "") for _, e in matches]
                        return {
                            "success": False,
                            "error": f"Multiple entries matched '{old_text}'. Be more specific.",
                            "matches": previews,
                        }

                idx = matches[0][0]
                old_entry = entries[idx]
                old_key = self._entry_key(old_entry)
                self._meta.get(target, {}).pop(old_key, None)
                entries.pop(idx)
                self._set_entries(target, entries)
            # 修复：释放读锁后由save_to_disk自身的写入锁保护持久化
            self.save_to_disk(target)
        except Exception as e:
            # 修复：添加异常处理，确保文件锁异常被捕获
            logger.error(f"Memory remove failed: {e}")
            return {"success": False, "error": str(e)}

        # 记录信号到记忆蒸馏系统（非关键操作，失败不阻塞主流程）
        try:
            from agent.memory_distillation import record_signal
            record_signal(old_entry, source="remove", score=0.5, query=f"remove:{target}")
        except Exception:
            pass

        return self._success_response(target, "Entry removed.")

    def format_for_system_prompt(self, target: str) -> Optional[str]:
        """
        Return the frozen snapshot for system prompt injection.

        This returns the state captured at load_from_disk() time, NOT the live
        state. Mid-session writes do not affect this. This keeps the system
        prompt stable across all turns, preserving the prefix cache.

        Returns None if the snapshot is empty (no entries at load time).
        """
        resolved = self._resolve_target(target)
        block = self._system_prompt_snapshot.get(resolved, "")
        return block if block else None

    def recall(self, query: str) -> Dict[str, Any]:
        """Search across all memory layers using hybrid FTS + simhash scoring.

        Returns top-k results ranked by relevance, grouped by layer.
        Uses cached simhash values for performance optimization.
        If query is empty, returns all entries across all layers.
        """
        # Handle empty query - return all entries instead of error
        if not query or not query.strip():
            results = []
            for target in VALID_TARGETS:
                for entry in self._entries.get(target, []):
                    results.append({
                        "target": target,
                        "content": entry,
                        "score": 1.0,
                        "fts_score": 1.0,
                        "vector_score": 1.0,
                    })
            results.sort(key=lambda r: r["content"])
            top = results[:8]
            return {
                "success": True,
                "query": "",
                "results": top,
                "total_matches": len(results),
                "note": "Empty query - showing all entries",
            }

        query_lower = query.lower().strip()
        query_words = _extract_tokens(query_lower)
        query_hash = simhash(query_lower)
        results = []

        for target in VALID_TARGETS:
            for entry in self._entries.get(target, []):
                entry_lower = entry.lower()
                # 修复：使用OrderedDict实现LRU淘汰，访问时移动到末尾（最近使用）
                cache_key = f"{target}:{self._entry_key(entry)}"
                if cache_key in self._simhash_cache:
                    entry_hash = self._simhash_cache[cache_key]
                    # LRU：将已访问的条目移到末尾，标记为最近使用
                    self._simhash_cache.move_to_end(cache_key)
                else:
                    entry_hash = simhash(entry_lower)
                    self._simhash_cache[cache_key] = entry_hash
                    # LRU淘汰：超出容量时删除最久未访问的条目（OrderedDict首部）
                    if len(self._simhash_cache) > self._simhash_cache_maxsize:
                        self._simhash_cache.popitem(last=False)
                
                fts_score = self._fts_score(entry_lower, query_lower, query_words)
                vector_score = simhash_similarity(query_hash, entry_hash)  # 整合: 改用模块级函数 [H5]
                # 修复：SimHash权重过高(0.45)，FTS关键词匹配更可靠
                # 调整为FTS 0.6 + SimHash 0.4，提高关键词匹配的权重
                hybrid_score = 0.6 * fts_score + 0.4 * vector_score
                if hybrid_score > 0.05:
                    results.append({
                        "target": target,
                        "content": entry,
                        "score": round(hybrid_score, 4),
                        "fts_score": round(fts_score, 4),
                        "vector_score": round(vector_score, 4),
                    })

        results.sort(key=lambda r: r["score"], reverse=True)
        top = results[:8]

        # 修复：仅对最终返回的top-8结果更新元数据（_touch_meta + _save_meta）
        # 原实现对所有匹配条目（可能远超8个）都更新元数据并持久化到磁盘，
        # 产生大量不必要的磁盘I/O。Ebbinghaus记忆衰减的访问刷新只需对
        # 实际返回给调用方的条目执行，未返回的条目不应被recall影响。
        for r in top:
            self._touch_meta(r["target"], r["content"])
        self._save_meta()

        return {
            "success": True,
            "query": query,
            "results": top,
            "total_matches": len(results),
        }

    @staticmethod
    def _fts_score(text: str, query_lower: str, query_words: set) -> float:
        """Score text against query using keyword matching and proximity.
        
        修复：调整权重分配，提高关键词覆盖率的权重，改善语义相关性判别
        """
        if not query_words:
            return 0.0

        text_words = _extract_tokens(text)
        overlap = query_words & text_words
        if not overlap:
            if query_lower in text:
                return 0.6
            return 0.0

        # 修复：增加关键词覆盖率和密度的权重，改善相似内容评分
        coverage = len(overlap) / len(query_words)
        density = len(overlap) / max(len(text_words), 1)
        exact_bonus = 1.0 if query_lower in text else 0.0
        # 调整权重：覆盖率70%，密度20%，精确匹配10%
        return min(1.0, coverage * 0.7 + density * 0.2 + exact_bonus * 0.1)

    # 整合: 删除 _simhash_similarity 静态方法，统一使用 utils.simhash_similarity [H5]
    # 旧调用 self._simhash_similarity(h1, h2) 已改为 simhash_similarity(h1, h2)

    # -- Internal helpers --

    def _success_response(self, target: str, message: str = None) -> Dict[str, Any]:
        entries = self._entries_for(target)
        current = self._char_count(target)
        limit = self._char_limit(target)
        pct = min(100, int((current / limit) * 100)) if limit > 0 else 0

        resp = {
            "success": True,
            "target": target,
            "entries": entries,
            "usage": f"{pct}% — {current:,}/{limit:,} chars",
            "entry_count": len(entries),
        }
        if message:
            resp["message"] = message
        return resp

    def _render_block(self, target: str, entries: List[str]) -> str:
        """Render a system prompt block with header and usage indicator."""
        if not entries:
            return ""

        limit = self._char_limit(target)
        content = ENTRY_DELIMITER.join(entries)
        current = len(content)
        pct = min(100, int((current / limit) * 100)) if limit > 0 else 0

        header = f"{TARGET_HEADERS.get(target, target.upper())} [{pct}% — {current:,}/{limit:,} chars]"
        separator = "═" * 46
        return f"{separator}\n{header}\n{separator}\n{content}"

    @staticmethod
    def _read_file(path: Path) -> List[str]:
        """Read a memory file and split into entries.

        No file locking needed: _write_file uses atomic rename, so readers
        always see either the previous complete file or the new complete file.
        """
        if not path.exists():
            return []
        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            import locale
            fallback = locale.getpreferredencoding(False)
            try:
                raw = path.read_text(encoding=fallback)
            except (UnicodeDecodeError, LookupError):
                raw = path.read_text(encoding="utf-8", errors="replace")
        except (OSError, IOError):
            return []

        if not raw.strip():
            return []

        # Use ENTRY_DELIMITER for consistency with _write_file. Splitting by "§"
        # alone would incorrectly split entries that contain "§" in their content.
        entries = [e.strip() for e in raw.split(ENTRY_DELIMITER)]
        return [e for e in entries if e]

    @staticmethod
    def _write_file(path: Path, entries: List[str]):
        """Write entries to a memory file using atomic temp-file + rename.

        Previous implementation used open("w") + flock, but "w" truncates the
        file *before* the lock is acquired, creating a race window where
        concurrent readers see an empty file. Atomic rename avoids this:
        readers always see either the old complete file or the new one.
        
        修复：Windows兼容性处理 - Windows下os.replace()可能因文件被占用而失败
        """
        content = ENTRY_DELIMITER.join(entries) if entries else ""
        try:
            # Write to temp file in same directory (same filesystem for atomic rename)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(path.parent), suffix=".tmp", prefix=".mem_"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(content)
                    f.flush()
                    os.fsync(f.fileno())
                
                # Windows安全替换策略：先备份旧文件，再替换，确保至少有一个完整版本始终存在
                # 原因：Windows上os.unlink+os.replace之间存在时间窗口，若进程在此期间崩溃，
                # 旧文件已被删除但新文件尚未就位，导致记忆文件丢失。
                # 策略：先原子重命名旧文件为.bak备份，再重命名新文件为目标文件，
                # 若第二步失败则从备份恢复，确保任何时刻至少有一个完整版本存在。
                # 如果备份步骤本身失败（如权限问题），回退到直接替换（仍比unlink+replace安全）
                if sys.platform == "win32":
                    backup_path = str(path) + ".bak"
                    backup_created = False
                    if path.exists():
                        try:
                            os.replace(str(path), backup_path)
                            backup_created = True
                        except OSError:
                            pass  # 备份失败时回退到直接替换
                    try:
                        os.replace(tmp_path, str(path))
                    except OSError:
                        if backup_created and os.path.exists(backup_path):
                            try:
                                os.replace(backup_path, str(path))
                            except OSError:
                                pass
                        raise
                    if backup_created:
                        try:
                            if os.path.exists(backup_path):
                                os.unlink(backup_path)
                        except OSError:
                            pass
                else:
                    os.replace(tmp_path, str(path))
            except BaseException:
                # Clean up temp file on any failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except (OSError, IOError) as e:
            raise RuntimeError(f"Failed to write memory file {path}: {e}")


def memory_tool(
    action: str,
    target: str = "facts",
    content: str = None,
    old_text: str = None,
    query: str = None,
    store: Optional[MemoryStore] = None,
) -> str:
    """
    Single entry point for the memory tool. Dispatches to MemoryStore methods.

    Returns JSON string with results.
    """
    if store is None:
        return tool_error("Memory is not available. It may be disabled in config or this environment.", success=False)

    resolved = store._resolve_target(target)
    if resolved not in VALID_TARGETS:
        return tool_error(f"Invalid target '{target}'. Use: {', '.join(VALID_TARGETS)}. ('memory' is alias for 'facts')", success=False)

    if action == "add":
        if not content:
            return tool_error("Content is required for 'add' action.", success=False)
        result = store.add(resolved, content)

    elif action == "replace":
        if not old_text:
            return tool_error("old_text is required for 'replace' action.", success=False)
        if not content:
            return tool_error("content is required for 'replace' action.", success=False)
        result = store.replace(resolved, old_text, content)

    elif action == "remove":
        if not old_text:
            return tool_error("old_text is required for 'remove' action.", success=False)
        result = store.remove(resolved, old_text)

    elif action == "recall":
        result = store.recall(query or content or "")

    else:
        return tool_error(f"Unknown action '{action}'. Use: add, replace, remove, recall", success=False)

    return json.dumps(result, ensure_ascii=False)


def check_memory_requirements() -> bool:
    """Check if memory is enabled in configuration.
    
    Memory tool requires memory_enabled or user_profile_enabled to be True
    in the agent configuration. This prevents the tool from being registered
    when memory is disabled, avoiding runtime errors.
    """
    try:
        from kunming_cli.config import load_config
        config = load_config()
        mem_config = config.get("memory", {})
        return mem_config.get("memory_enabled", False) or mem_config.get("user_profile_enabled", False)
    except Exception:
        # If we can't load config, assume memory is disabled to be safe
        return False


# =============================================================================
# OpenAI Function-Calling Schema
# =============================================================================

MEMORY_SCHEMA = {
    "name": "memory",
    "description": (
        "Save durable information to persistent memory that survives across sessions. "
        "Memory is injected into future turns, so keep it compact and focused on facts "
        "that will still matter later.\n\n"
        "THREE-LAYER ARCHITECTURE:\n"
        "- 'facts': stable knowledge about the world — environment, tools, project conventions, API quirks\n"
        "- 'experiences': episodic records — problem-solving steps, what worked/failed, operation outcomes\n"
        "- 'models': learned rules and patterns — decision strategies, abstracted from experiences\n"
        "- 'user': who the user is — name, role, preferences, communication style, pet peeves\n\n"
        "WHEN TO SAVE (do this proactively, don't wait to be asked):\n"
        "- User corrects you or says 'remember this' / 'don't do that again'\n"
        "- User shares a preference, habit, or personal detail → 'user' target\n"
        "- You discover something about the environment (OS, tools, project structure) → 'facts'\n"
        "- You solve a problem, learn what works/doesn't → 'experiences'\n"
        "- You identify a reusable pattern or rule → 'models'\n\n"
        "PRIORITY: User preferences and corrections > environment facts > procedural knowledge. "
        "The most valuable memory prevents the user from having to repeat themselves.\n\n"
        "ACTIONS:\n"
        "- add: create a new entry in the specified target\n"
        "- replace: update an existing entry (old_text identifies it)\n"
        "- remove: delete an entry (old_text identifies it)\n"
        "- recall: search across all memory layers for relevant entries\n\n"
        "Do NOT save task progress, session outcomes, completed-work logs, or temporary TODO "
        "state to memory; use session_search to recall those from past transcripts.\n\n"
        "SKIP: trivial/obvious info, things easily re-discovered, raw data dumps, and temporary task state."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "replace", "remove", "recall"],
                "description": "The action to perform. 'recall' searches across all layers."
            },
            "target": {
                "type": "string",
                "enum": ["facts", "experiences", "models", "user", "memory"],
                "description": "Which memory layer: 'facts' (environment knowledge), 'experiences' (problem-solving records), 'models' (learned rules), 'user' (user profile). 'memory' is alias for 'facts'."
            },
            "content": {
                "type": "string",
                "description": "The entry content. Required for 'add' and 'replace'."
            },
            "old_text": {
                "type": "string",
                "description": "Short unique substring identifying the entry to replace or remove."
            },
            "query": {
                "type": "string",
                "description": "Search query for 'recall' action. Returns relevant entries across all layers."
            },
        },
        "required": ["action", "target"],
    },
}


# --- Registry ---
from tools.registry import registry, tool_error

registry.register(
    name="memory",
    toolset="memory",
    schema=MEMORY_SCHEMA,
    handler=lambda args, **kw: memory_tool(
        action=args.get("action", ""),
        target=args.get("target", "facts"),
        content=args.get("content"),
        old_text=args.get("old_text"),
        query=args.get("query"),
        store=kw.get("store")),
    check_fn=check_memory_requirements,
    emoji="🧠",
    is_agent_tool=True,
)




