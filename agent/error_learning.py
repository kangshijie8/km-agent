"""
Error Learning Module - Learn from mistakes and user corrections.

Detects when the user corrects the agent, logs the error with context,
and retrieves relevant past errors at session start to avoid repeating
mistakes. Recurring errors are automatically promoted to the models layer.

Three components:
  1. Correction detection: identify when user corrects agent output
  2. Error logging: persist errors with full context to error_log.json
  3. Experience retrieval: fetch relevant past errors when starting tasks
"""

import hashlib
import json
import logging
import os
import re
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from kunming_constants import get_kunming_home
from utils import _extract_tokens

try:
    import fcntl
except ImportError:
    fcntl = None

logger = logging.getLogger(__name__)

_CORRECTION_PATTERNS = [
    (r"(?:no|don't|stop|wrong|incorrect|that's wrong|not like that)", "explicit_rejection"),
    (r"(?:不用.*(?:应该|要|得)|不要.*(?:应该|要|得)|错了[，,].*|不对[，,].*(?:应该|要|得))", "explicit_rejection_cjk"),
    (r"(?:instead|rather|actually|I meant|应该是|其实是|而是)", "redirect"),
    (r"(?:I said|I told you|as I mentioned|我说过|我之前说过)", "reference_previous"),
    (r"(?:fix|correct|change it to|修改|改正|换成)", "fix_request"),
    (r"(?:the (?:correct|right|proper) (?:way|approach|method) is|正确做法是)", "correct_approach"),
]

_ERROR_LOG_FILE = "error_log.json"
_MAX_ERROR_ENTRIES = 200
_PROMOTION_THRESHOLD = 3


def _error_log_path() -> Path:
    return get_kunming_home() / "memories" / _ERROR_LOG_FILE


@contextmanager
def _error_lock():
    lock_path = _error_log_path().with_suffix(".json.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = open(lock_path, "w")
    try:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_EX)
        else:
            import msvcrt
            _deadline = time.monotonic() + 10
            while time.monotonic() < _deadline:
                try:
                    msvcrt.locking(fd.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
            else:
                fd.close()
                raise TimeoutError("Error log lock acquisition timed out")
        yield
    finally:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_UN)
        else:
            try:
                import msvcrt
                msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        fd.close()


def _load_error_log() -> Dict[str, Any]:
    path = _error_log_path()
    if not path.exists():
        return {"version": 1, "errors": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "errors": {}}


def _save_error_log(data: Dict[str, Any]) -> None:
    path = _error_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp", prefix=".err_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def detect_correction(user_message: str, assistant_message: str) -> Optional[Dict[str, Any]]:
    """Detect if the user is correcting the agent's previous output.

    Returns a correction dict if detected, None otherwise.
    """
    if not user_message or not assistant_message:
        return None

    user_lower = user_message.lower()
    matched_patterns = []
    for pattern, pid in _CORRECTION_PATTERNS:
        if re.search(pattern, user_lower, re.IGNORECASE):
            matched_patterns.append(pid)

    if not matched_patterns:
        return None

    return {
        "type": "correction",
        "patterns": matched_patterns,
        "user_message": user_message[:500],
        "assistant_message": assistant_message[:500],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "confidence": min(1.0, len(matched_patterns) * 0.35 + 0.3),
    }


def log_error(
    error_type: str,
    context: str,
    what_was_wrong: str,
    what_should_be: str = "",
    task_context: str = "",
) -> Dict[str, Any]:
    """Log an error or correction for future learning.

    Args:
        error_type: 'correction', 'tool_failure', 'logic_error', etc.
        context: What the agent was trying to do.
        what_was_wrong: What the agent did wrong.
        what_should_be: What the correct approach is.
        task_context: Broader task context for retrieval.

    Returns:
        Dict with logging result.
    """
    import hashlib
    key = hashlib.sha256(f"{what_was_wrong}:{what_should_be}".encode()).hexdigest()[:16]

    with _error_lock():
        log = _load_error_log()
        errors = log.setdefault("errors", {})

        now_iso = datetime.now(timezone.utc).isoformat()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if key in errors:
            entry = errors[key]
            entry["occurrence_count"] = entry.get("occurrence_count", 0) + 1
            entry["last_seen"] = now_iso
            days = set(entry.get("seen_days", []))
            days.add(today)
            entry["seen_days"] = sorted(days)[-16:]
            if what_should_be and not entry.get("what_should_be"):
                entry["what_should_be"] = what_should_be
        else:
            errors[key] = {
                "error_type": error_type,
                "context": context[:300],
                "what_was_wrong": what_was_wrong[:300],
                "what_should_be": what_should_be[:300],
                "task_context": task_context[:200],
                "occurrence_count": 1,
                "first_seen": now_iso,
                "last_seen": now_iso,
                "seen_days": [today],
                "promoted": False,
            }

        if len(errors) > _MAX_ERROR_ENTRIES:
            sorted_errors = sorted(errors.items(), key=lambda x: x[1].get("last_seen", ""), reverse=True)
            errors = dict(sorted_errors[:_MAX_ERROR_ENTRIES])
            log["errors"] = errors

        if errors[key]["occurrence_count"] >= _PROMOTION_THRESHOLD and not errors[key].get("promoted"):
            _promote_error_to_models(errors[key])
            errors[key]["promoted"] = True

        log["updated_at"] = now_iso
        _save_error_log(log)

    return {
        "success": True,
        "key": key,
        "occurrence_count": errors[key]["occurrence_count"],
        "promoted": errors[key].get("promoted", False),
    }


def _promote_error_to_models(error_entry: Dict[str, Any]) -> None:
    """Promote a recurring error to the MODELS.md layer as a learned rule."""
    from tools.memory_tool import MemoryStore
    store = MemoryStore()
    store.load_from_disk()

    wrong = error_entry.get("what_was_wrong", "")
    correct = error_entry.get("what_should_be", "")
    rule = f"AVOID: {wrong}"
    if correct:
        rule += f" → INSTEAD: {correct}"

    store.add("models", rule)
    logger.info("Promoted recurring error to models: %s", rule[:80])


def _simhash(text: str, hashbits: int = 64) -> int:
    v = [0] * hashbits
    compound_pattern = re.compile(r'[a-zA-Z][\w.-]+[\w]')
    cjk_pattern = re.compile(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]{1,}')
    tokens = [m.group() for m in compound_pattern.finditer(text.lower())]
    tokens += [m.group() for m in cjk_pattern.finditer(text)]
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


def _simhash_similarity(hash1: int, hash2: int, hashbits: int = 64) -> float:
    if hash1 == 0 and hash2 == 0:
        return 0.0
    xor = hash1 ^ hash2
    diff_bits = bin(xor).count('1')
    return 1.0 - (diff_bits / hashbits)


def retrieve_relevant_errors(query: str, limit: int = 3) -> List[Dict[str, Any]]:
    """Uses hybrid scoring: keyword matching (60%) + SimHash semantic similarity (40%)."""
    if not query.strip():
        return []

    log = _load_error_log()
    errors = log.get("errors", {})
    if not errors:
        return []

    query_lower = query.lower()
    query_words = _extract_tokens(query_lower)
    query_hash = _simhash(query_lower)

    scored = []
    for key, entry in errors.items():
        if entry.get("promoted"):
            continue
        entry_text = f"{entry.get('context', '')} {entry.get('what_was_wrong', '')} {entry.get('task_context', '')}".lower()
        entry_words = _extract_tokens(entry_text)
        overlap = query_words & entry_words

        keyword_score = 0.0
        if overlap:
            keyword_score = len(overlap) / max(len(query_words), 1)
        if query_lower in entry_text:
            keyword_score += 0.3

        sem_score = _simhash_similarity(query_hash, _simhash(entry_text))

        combined = 0.6 * keyword_score + 0.4 * sem_score
        combined += min(0.3, entry.get("occurrence_count", 1) * 0.1)
        if combined > 0.08:
            scored.append((combined, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [entry for _, entry in scored[:limit]]


def get_error_summary() -> Dict[str, Any]:
    """Get a summary of the error log for status display."""
    log = _load_error_log()
    errors = log.get("errors", {})
    total = len(errors)
    promoted = sum(1 for e in errors.values() if e.get("promoted"))
    recurring = sum(1 for e in errors.values() if e.get("occurrence_count", 0) >= 2)
    return {
        "total_errors": total,
        "promoted_to_models": promoted,
        "recurring_errors": recurring,
        "active_errors": total - promoted,
    }
