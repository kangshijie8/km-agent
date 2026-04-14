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

import hashlib
import json
import logging
import math
import os
import re
import struct
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from kunming_constants import get_kunming_home
from typing import Dict, Any, List, Optional, Tuple

try:
    import fcntl
except ImportError:
    fcntl = None

logger = logging.getLogger(__name__)

# Where memory files live — resolved dynamically so profile overrides
# (KUNMING_HOME env var changes) are always respected.  The old module-level
# constant was cached at import time and could go stale if a profile switch
# happened after the first import.
def get_memory_dir() -> Path:
    """Return the profile-scoped memories directory."""
    return get_kunming_home() / "memories"

# Backward-compatible alias — gateway/run.py imports this at runtime inside
# a function body, so it gets the correct snapshot for that process.  New code
# should prefer get_memory_dir().
MEMORY_DIR = get_memory_dir()

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
        """
        meta = self._get_meta(target, content)
        if not meta:
            return 1.0
        created = meta.get("created_at", time.time())
        last_accessed = meta.get("last_accessed", created)
        access_count = meta.get("access_count", 1)
        importance = meta.get("importance", 0.5)

        age_days = (time.time() - created) / 86400.0
        access_boost = 1.0 + math.log1p(access_count) * 0.3
        effective_half_life = _EBINGHAUS_HALF_LIFE_DAYS * access_boost * (0.5 + importance)
        retention = math.exp(-0.693 * age_days / effective_half_life)
        return max(0.0, min(1.0, retention))

    def decay_memories(self, target: str) -> int:
        """Remove entries below Ebbinghaus retention threshold.

        Protected entries (importance >= 0.8 or containing keywords like
        'preference', 'always', 'never', 'must') are never decayed.
        Returns count of removed entries.
        """
        _PROTECTED_KEYWORDS = ("preference", "always", "never", "must", "required", "important", "critical")
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
    @contextmanager
    def _file_lock(path: Path):
        lock_path = path.with_suffix(path.suffix + ".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = open(lock_path, "w")
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_EX)
            else:
                import msvcrt
                deadline = time.monotonic() + 10
                fd.seek(0)
                while time.monotonic() < deadline:
                    try:
                        msvcrt.locking(fd.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except (OSError, IOError):
                        time.sleep(0.05)
                else:
                    raise TimeoutError("File lock acquisition timed out")
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_UN)
            else:
                import msvcrt
                try:
                    fd.seek(0)
                    msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
                except (OSError, IOError):
                    pass
            fd.close()

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
        """Persist entries to the appropriate file. Called after every mutation."""
        get_memory_dir().mkdir(parents=True, exist_ok=True)
        self._write_file(self._path_for(target), self._entries_for(target))
        # Persist Ebbinghaus metadata
        try:
            with open(self._meta_path, "w", encoding="utf-8") as f:
                json.dump(self._meta, f)
        except Exception:
            pass  # Meta persistence is best-effort

    def _entries_for(self, target: str) -> List[str]:
        resolved = self._resolve_target(target)
        return self._entries.get(resolved, [])

    def _set_entries(self, target: str, entries: List[str]):
        resolved = self._resolve_target(target)
        self._entries[resolved] = entries

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

        with self._file_lock(self._path_for(target)):
            # Re-read from disk under lock to pick up writes from other sessions
            self._reload_target(target)

            entries = self._entries_for(target)
            limit = self._char_limit(target)

            # Reject exact duplicates
            if content in entries:
                return self._success_response(target, "Entry already exists (no duplicate added).")

            # Calculate what the new total would be
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
            self.save_to_disk(target)
            self._init_meta(target, content)

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

        with self._file_lock(self._path_for(target)):
            self._reload_target(target)

            entries = self._entries_for(target)
            matches = [(i, e) for i, e in enumerate(entries) if old_text in e]

            if not matches:
                return {"success": False, "error": f"No entry matched '{old_text}'."}

            if len(matches) > 1:
                # If all matches are identical (exact duplicates), operate on the first one
                unique_texts = set(e for _, e in matches)
                if len(unique_texts) > 1:
                    previews = [e[:80] + ("..." if len(e) > 80 else "") for _, e in matches]
                    return {
                        "success": False,
                        "error": f"Multiple entries matched '{old_text}'. Be more specific.",
                        "matches": previews,
                    }
                # All identical -- safe to replace just the first

            idx = matches[0][0]
            limit = self._char_limit(target)

            # Check that replacement doesn't blow the budget
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

            entries[idx] = new_content
            self._set_entries(target, entries)
            self.save_to_disk(target)

        return self._success_response(target, "Entry replaced.")

    def remove(self, target: str, old_text: str) -> Dict[str, Any]:
        """Remove the entry containing old_text substring."""
        old_text = old_text.strip()
        if not old_text:
            return {"success": False, "error": "old_text cannot be empty."}

        with self._file_lock(self._path_for(target)):
            self._reload_target(target)

            entries = self._entries_for(target)
            matches = [(i, e) for i, e in enumerate(entries) if old_text in e]

            if not matches:
                return {"success": False, "error": f"No entry matched '{old_text}'."}

            if len(matches) > 1:
                # If all matches are identical (exact duplicates), remove the first one
                unique_texts = set(e for _, e in matches)
                if len(unique_texts) > 1:
                    previews = [e[:80] + ("..." if len(e) > 80 else "") for _, e in matches]
                    return {
                        "success": False,
                        "error": f"Multiple entries matched '{old_text}'. Be more specific.",
                        "matches": previews,
                    }
                # All identical -- safe to remove just the first

            idx = matches[0][0]
            entries.pop(idx)
            self._set_entries(target, entries)
            self.save_to_disk(target)

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
        """
        if not query.strip():
            return {"success": False, "error": "Query cannot be empty."}

        query_lower = query.lower().strip()
        query_words = set(re.findall(r'\w+', query_lower))
        query_hash = self._simhash(query_lower)
        results = []

        for target in VALID_TARGETS:
            for entry in self._entries.get(target, []):
                entry_lower = entry.lower()
                fts_score = self._fts_score(entry_lower, query_lower, query_words)
                vector_score = self._simhash_similarity(query_hash, self._simhash(entry_lower))
                hybrid_score = 0.35 * fts_score + 0.65 * vector_score
                if hybrid_score > 0.05:
                    results.append({
                        "target": target,
                        "content": entry,
                        "score": round(hybrid_score, 4),
                        "fts_score": round(fts_score, 4),
                        "vector_score": round(vector_score, 4),
                    })
                    self._touch_meta(target, entry)

        results.sort(key=lambda r: r["score"], reverse=True)
        top = results[:8]

        return {
            "success": True,
            "query": query,
            "results": top,
            "total_matches": len(results),
        }

    @staticmethod
    def _fts_score(text: str, query_lower: str, query_words: set) -> float:
        """Score text against query using keyword matching and proximity."""
        if not query_words:
            return 0.0

        text_words = set(re.findall(r'\w+', text))
        overlap = query_words & text_words
        if not overlap:
            if query_lower in text:
                return 0.6
            return 0.0

        coverage = len(overlap) / len(query_words)
        density = len(overlap) / max(len(text_words), 1)
        exact_bonus = 1.0 if query_lower in text else 0.0
        return min(1.0, coverage * 0.6 + density * 0.2 + exact_bonus * 0.2)

    @staticmethod
    def _simhash(text: str, hashbits: int = 64) -> int:
        """Compute SimHash fingerprint for approximate similarity detection.

        Zero-dependency vector-like similarity using hash-based feature extraction.
        """
        v = [0] * hashbits
        tokens = re.findall(r'\w{2,}', text.lower())
        if not tokens:
            return 0
        for token in tokens:
            h = int(hashlib.md5(token.encode()).hexdigest(), 16)
            for i in range(hashbits):
                if h & (1 << i):
                    v[i] += 1
                else:
                    v[i] -= 1
        fingerprint = 0
        for i in range(hashbits):
            if v[i] > 0:
                fingerprint |= (1 << i)
        return fingerprint

    @staticmethod
    def _simhash_similarity(hash1: int, hash2: int, hashbits: int = 64) -> float:
        """Compute similarity between two SimHash fingerprints (0-1)."""
        if hash1 == 0 and hash2 == 0:
            return 0.0
        xor = hash1 ^ hash2
        diff_bits = bin(xor).count('1')
        return 1.0 - (diff_bits / hashbits)

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
                os.replace(tmp_path, str(path))  # Atomic on same filesystem
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
    """Memory tool has no external requirements -- always available."""
    return True


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




