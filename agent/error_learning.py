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
import re
import logging
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from kunming_constants import get_kunming_home, utc_now_iso  # 整合: 使用统一时间戳函数，与memory_distillation保持一致 [T1]
from utils import _extract_tokens

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils import simhash, simhash_similarity, file_lock, atomic_json_write  # 整合: 使用统一原子写入，消除本地 _save_error_log 重复实现 [J1]
from kunming_constants import HYBRID_SEARCH_FTS_WEIGHT, HYBRID_SEARCH_VECTOR_WEIGHT  # 整合: 使用统一搜索权重 [S1]

logger = logging.getLogger(__name__)

# 修复：改进纠正检测模式
# - 英文"no"改为\bno[,!.\s]排除"no problem"等误触发
# - 添加中文模式：不对、别、重新、换、不是这样、搞反了
# - 添加日文模式：違う、直して、違います
_CORRECTION_PATTERNS = [
    (r"\bno[,!.\s]|don't|stop|wrong|incorrect|that's wrong|not like that", "explicit_rejection"),
    # 修复：原模式"错了[，,].*"要求"错了"后必须跟逗号，导致单独说"错了"无法检测
    # 改为"错了"可独立出现或后跟任意内容；"不对"也可独立出现
    (r"不用.*(?:应该|要|得)|不要.*(?:应该|要|得)|错了|不对|别.*了|搞反了", "explicit_rejection_cjk"),
    (r"instead|rather|actually|I meant|应该是|其实是|而是|重新|换一个|不是这样", "redirect"),
    (r"I said|I told you|as I mentioned|我说过|我之前说过", "reference_previous"),
    (r"fix|correct|change it to|修改|改正|换成", "fix_request"),
    (r"the (?:correct|right|proper) (?:way|approach|method) is|正确做法是", "correct_approach"),
    (r"you (?:misunderstood|misinterpreted)|that's not (?:it|what|how)", "misunderstanding"),
    (r"不是这个|搞错了|理解错了", "misunderstanding_cjk"),
    (r"違う|直して|違います", "explicit_rejection_ja"),
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
    with file_lock(lock_path, timeout=10.0):
        yield


def _load_error_log() -> Dict[str, Any]:
    path = _error_log_path()
    if not path.exists():
        return {"version": 1, "errors": {}}
    try:
        content = path.read_text(encoding="utf-8")
        if not content.strip():
            return {"version": 1, "errors": {}}
        data = json.loads(content)
        if not isinstance(data, dict):
            return {"version": 1, "errors": {}}
        if "errors" not in data:
            data["errors"] = {}
        return data
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        logger.warning(f"Failed to load error log: {e}. Starting fresh.")
        return {"version": 1, "errors": {}}


# 整合: 删除本地 _save_error_log()，使用 utils.atomic_json_write [J1]
# 原定义: def _save_error_log(data) — tempfile + fsync + os.replace，与 atomic_json_write 功能等价
# 注意: 原函数返回 bool 表示成功/失败，atomic_json_write 在失败时抛异常，调用方需适配


def detect_correction(user_message: str, assistant_message: str) -> Optional[Dict[str, Any]]:
    """Detect if the user is correcting the agent's previous output.

    Returns a correction dict if detected, None otherwise.
    
    修复：增加置信度阈值检查，避免误判普通交流为纠正
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
    
    # 修复：原公式 len(matched_patterns) * 0.25 + 0.3 导致单模式匹配时
    # confidence = 0.55 < 0.7 阈值，直接返回None。用户说"错了"/"wrong"等
    # 明确纠正信号时系统完全无法检测到纠正，必须同时匹配至少2个模式才触发，
    # 这是纠正检测最关键的bug。调整公式为 len * 0.35 + 0.4，单模式 = 0.75 >= 0.7
    # 同时对 explicit_rejection 类模式（直接否定信号）给予额外加分，
    # 因为"错了"/"wrong"/"違う"等词本身就是极强纠正信号，不应被阈值屏蔽。
    _EXPLICIT_REJECTION_IDS = {"explicit_rejection", "explicit_rejection_cjk", "explicit_rejection_ja"}
    has_explicit_rejection = any(pid in _EXPLICIT_REJECTION_IDS for pid in matched_patterns)
    confidence = min(1.0, len(matched_patterns) * 0.35 + 0.4 + (0.15 if has_explicit_rejection else 0.0))
    # 修复：置信度阈值从0.7降为0.5，与run_agent.py中的检查阈值保持一致。
    # 原阈值0.7导致部分被run_agent.py（阈值0.5）接受的修正检测被error_learning拒绝，
    # 两个模块阈值不一致造成漏检。选择0.5（更宽松）因为漏检比误检更危险——
    # 漏检意味着agent重复犯错而无法学习修正，误检最多产生一条多余的错误记录。
    if confidence < 0.5:
        return None

    return {
        "type": "correction",
        "patterns": matched_patterns,
        "user_message": user_message[:500],
        "assistant_message": assistant_message[:500],
        "timestamp": utc_now_iso(),
        "confidence": confidence,
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
    key = hashlib.sha256(f"{what_was_wrong}:{what_should_be}".encode()).hexdigest()[:16]

    with _error_lock():
        log = _load_error_log()
        errors = log.setdefault("errors", {})

        now_iso = utc_now_iso()
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
        try:
            atomic_json_write(_error_log_path(), log)  # 整合: 使用统一原子写入 [J1]
        except Exception as e:
            logger.warning(f"Failed to save error log: {e}")  # 整合: 适配原 _save_error_log 的 bool 返回值语义 [J1]

    return {
        "success": True,
        "key": key,
        "occurrence_count": errors[key]["occurrence_count"],
        "promoted": errors[key].get("promoted", False),
    }


def _promote_error_to_models(error_entry: Dict[str, Any]) -> None:
    """Promote a recurring error to the MODELS.md layer as a learned rule.

    [并发保护] 使用memory_lock保护写入，防止与蒸馏/其他会话的并发写入互相覆盖。
    原实现：直接创建MemoryStore并add，无锁保护，若蒸馏同时运行会覆盖对方的写入。
    修复：在锁内reload+add(_skip_lock=True)，确保基于最新数据写入。
    """
    from tools.memory_tool import MemoryStore
    store = MemoryStore()
    store.load_from_disk()

    wrong = error_entry.get("what_was_wrong", "")
    correct = error_entry.get("what_should_be", "")
    rule = f"AVOID: {wrong}"
    if correct:
        rule += f" → INSTEAD: {correct}"

    # [并发保护] 在锁内reload+add，防止并发写入覆盖
    with store.memory_lock("models"):
        store._reload_target("models")
        store.add("models", rule, _skip_lock=True)
    logger.info("Promoted recurring error to models: %s", rule[:80])





def retrieve_relevant_errors(query: str, limit: int = 3) -> List[Dict[str, Any]]:
    """Uses hybrid scoring via HYBRID_SEARCH_FTS_WEIGHT/HYBRID_SEARCH_VECTOR_WEIGHT constants
    (currently FTS=0.6 + Vector=0.4), plus occurrence and promotion bonuses."""
    if not query.strip():
        return []

    log = _load_error_log()
    errors = log.get("errors", {})
    if not errors:
        return []

    query_lower = query.lower()
    query_words = _extract_tokens(query_lower)
    query_hash = simhash(query_lower)

    scored = []
    for key, entry in errors.items():
        # 修复：不再跳过已提升（promoted）的错误。
        # 已提升的错误是反复出现>=3次并被验证的模式，正是最应该作为
        # 警告展示给agent的高价值信息。跳过它们意味着agent无法从
        # 最关键的已验证错误模式中获益，反而只能看到未验证的低频错误。
        # 改为对promoted错误给予额外0.2相关性加分，因为它们是经过
        # 验证的高频错误模式，最应被展示。
        entry_text = f"{entry.get('context', '')} {entry.get('what_was_wrong', '')} {entry.get('task_context', '')}".lower()
        entry_words = _extract_tokens(entry_text)
        overlap = query_words & entry_words

        keyword_score = 0.0
        if overlap:
            keyword_score = len(overlap) / max(len(query_words), 1)
        if query_lower in entry_text:
            keyword_score += 0.3

        sem_score = simhash_similarity(query_hash, simhash(entry_text))

        combined = HYBRID_SEARCH_FTS_WEIGHT * keyword_score + HYBRID_SEARCH_VECTOR_WEIGHT * sem_score  # 整合: 使用统一搜索权重常量 [S1]
        combined += min(0.3, entry.get("occurrence_count", 1) * 0.1)
        # 已提升的错误是经过验证的反复出现模式，给予额外相关性加分
        if entry.get("promoted"):
            combined += 0.2
        if combined > 0.15:
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
