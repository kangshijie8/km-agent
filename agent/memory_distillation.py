"""
Memory Distillation — offline consolidation of short-term signals into long-term memory.

Three-phase model mirroring sleep-stage memory consolidation:
  - Light phase: collect recent signals (session transcripts, daily notes)
  - Deep phase: score candidates by multi-dimensional weighted formula, promote
    high-confidence entries into FACTS.md / EXPERIENCES.md / MODELS.md
  - REM phase: extract recurring patterns and themes across memories

The distillation runs as a cron job (default: daily at 3 AM) or on-demand via
the /distill slash command. It operates on the FACTS.md / EXPERIENCES.md / MODELS.md / USER.md files that
the MemoryStore manages, and writes results atomically so concurrent sessions
are not disrupted.

Scoring formula (6 dimensions, based on forgetting curve + spaced repetition):
  score = W_freq * frequency + W_rel * relevance + W_div * diversity
        + W_rec * recency     + W_con * consolidation + W_cpt * conceptual

  - frequency:    how often the signal appeared (log-scaled)
  - relevance:    average retrieval quality score
  - diversity:    number of distinct contexts / days the signal appeared in
  - recency:      exponential decay with configurable half-life (forgetting curve)
  - consolidation: spacing effect — repeated across multiple days is stronger
  - conceptual:   number of distinct concept tags extracted from the snippet

Threshold gating prevents low-quality promotions:
  - min_score:         0.65  (composite score floor, overridable via config)
  - min_signal_count:  2     (must appear at least N times)
  - min_unique_days:   1     (must span at least N distinct days)
  - max_age_days:      30    (ignore stale signals)
"""

import hashlib
import json
import logging
import math
import sys
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from kunming_constants import get_kunming_home, _MEMORY_PROTECTED_KEYWORDS, utc_now_iso, _EBINGHAUS_HALF_LIFE_DAYS, ebbinghaus_retention  # [C1修复] 补充ebbinghaus_retention导入，原缺失导致_score_candidates()在Deep阶段NameError，蒸馏完全失效

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils import file_lock, _extract_tokens, atomic_json_write, extract_keywords_cjk, jaccard_similarity  # [R2-K1] 导入统一关键词提取函数; [R2-J1] 导入统一Jaccard相似度函数

logger = logging.getLogger(__name__)

_DISTILL_DIR_NAME = "distillation"
_SIGNALS_FILE = "signals.json"
_STATE_FILE = "state.json"

W_FREQ = 0.24
W_REL = 0.30
W_DIV = 0.15
W_REC = 0.15
W_CON = 0.10
W_CPT = 0.06

# 修复: 重命名避免与全局DEFAULT_CONFIG同名混淆 [M15]
_DISTILL_DEFAULT_CONFIG = {
    "enabled": True,
    "schedule": "0 3 * * *",
    "min_score": 0.65,
    "min_signal_count": 2,
    "min_unique_days": 1,
    "max_age_days": 30,
    "recency_half_life_days": _EBINGHAUS_HALF_LIFE_DAYS,  # [R2-M2] 使用统一常量，避免硬编码14与kunming_constants不同步
    "max_promotions_per_run": 8,
    "lookback_days": 7,
    "llm_assisted_rem": True,
    "decay_on_distill": True,
}


def _distill_dir() -> Path:
    return get_kunming_home() / _DISTILL_DIR_NAME


def _signals_path() -> Path:
    return _distill_dir() / _SIGNALS_FILE


def _state_path() -> Path:
    return _distill_dir() / _STATE_FILE





def _load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default if default is not None else {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default if default is not None else {}


# 整合: 删除本地 _save_json()，使用 utils.atomic_json_write [J1]
# 原定义: def _save_json(path, data) — tempfile + fsync + os.replace，与 atomic_json_write 功能完全等价


# 整合: 删除本地 _now_iso()，使用 kunming_constants.utc_now_iso [T1]
# 原定义: def _now_iso() -> str: return datetime.now(timezone.utc).isoformat()


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _extract_concept_tags(text: str, max_tags: int = 8) -> List[str]:
    """Extract concept tags from text using lightweight heuristics.

    Multi-language aware: handles CJK characters, compound terms (hyphen/dot joined),
    and filters common stop words.

    [R2-K1] 委托给统一函数extract_keywords_cjk，消除本地重复实现
    """
    return extract_keywords_cjk(text, max_keywords=max_tags)


# [R2-J1] 删除本地_jaccard_similarity()，改用utils.jaccard_similarity
# 原实现：接受两个字符串参数，内部调用_extract_tokens分词后计算集合Jaccard
# 新方式：调用方自行分词，传入集合给jaccard_similarity()
# 保留辅助函数封装分词+相似度计算，方便现有调用点使用
def _jaccard_text_similarity(a: str, b: str) -> float:
    """Jaccard similarity on token sets. Used for semantic dedup.

    [R2-J1] 封装：分词 + 调用统一jaccard_similarity，替代原本地实现
    """
    wa = _extract_tokens(a.lower())
    wb = _extract_tokens(b.lower())
    return jaccard_similarity(wa, wb)


def record_signal(
    snippet: str,
    source: str = "recall",
    score: float = 0.5,
    query: str = "",
) -> None:
    """Record a short-term memory signal for later distillation.

    Called by the memory tool when entries are accessed or written, and by
    session search when results are retrieved. Signals accumulate in
    signals.json and are scored during the next distillation run.

    Args:
        snippet: The memory text fragment (max 280 chars recommended).
        source: Origin of the signal — "recall" (retrieved), "write" (saved),
                "session" (transcript), "daily" (daily note).
        score: Quality/relevance score 0-1 for this signal.
        query: The query that triggered this signal (for diversity tracking).
    """
    snippet = snippet.strip()[:280]
    if not snippet:
        return

    signals_path = _signals_path()
    with file_lock(str(signals_path)):
        signals = _load_json(signals_path, {"version": 1, "entries": {}})
        entries = signals.setdefault("entries", {})

        key = f"sig:{hashlib.sha256(snippet.encode()).hexdigest()[:16]}"
        today = _today_str()

        if key in entries:
            entry = entries[key]
            entry["signal_count"] = entry.get("signal_count", 0) + 1
            entry["total_score"] = entry.get("total_score", 0.0) + score
            entry["max_score"] = max(entry.get("max_score", 0.0), score)
            entry["last_seen"] = utc_now_iso()  # 整合: 使用统一时间戳函数 [T1]
            days = set(entry.get("seen_days", []))
            days.add(today)
            entry["seen_days"] = sorted(days)[-16:]
            if query:
                qhashes = entry.get("query_hashes", [])
                qh = hashlib.sha256(query.encode()).hexdigest()[:16]
                if qh not in qhashes:
                    qhashes.append(qh)
                entry["query_hashes"] = qhashes[-32:]
            sources = entry.get("sources", [])
            if source not in sources:
                sources.append(source)
            entry["sources"] = sources
        else:
            entries[key] = {
                "snippet": snippet,
                "signal_count": 1,
                "total_score": score,
                "max_score": score,
                "first_seen": utc_now_iso(),  # 整合: 使用统一时间戳函数 [T1]
                "last_seen": utc_now_iso(),  # 整合: 使用统一时间戳函数 [T1]
                "seen_days": [today],
                "query_hashes": [hashlib.sha256(query.encode()).hexdigest()[:16]] if query else [],
                "concept_tags": _extract_concept_tags(snippet),
                "sources": [source],
            }

        signals["updated_at"] = utc_now_iso()  # 整合: 使用统一时间戳函数 [T1]
        atomic_json_write(signals_path, signals)  # 整合: 使用统一原子写入 [J1]


def _score_candidates(
    entries: Dict[str, Dict],
    config: Dict[str, Any],
) -> List[Dict]:
    """Score and rank distillation candidates using the 6-dimension formula.

    Returns candidates sorted by descending score, filtered by thresholds.
    """
    now = datetime.now(timezone.utc)
    half_life = config.get("recency_half_life_days", _EBINGHAUS_HALF_LIFE_DAYS)  # [R2-M2] 使用统一常量作为默认值
    min_score = config.get("min_score", _DISTILL_DEFAULT_CONFIG.get("min_score", 0.65))
    min_signals = config.get("min_signal_count", _DISTILL_DEFAULT_CONFIG.get("min_signal_count", 2))
    min_days = config.get("min_unique_days", _DISTILL_DEFAULT_CONFIG.get("min_unique_days", 1))
    max_age = config.get("max_age_days", 30)

    candidates = []
    for key, entry in entries.items():
        if entry.get("promoted_at"):
            continue

        signal_count = entry.get("signal_count", 0)
        if signal_count < min_signals:
            continue

        seen_days = entry.get("seen_days", [])
        if len(seen_days) < min_days:
            continue

        first_seen_str = entry.get("first_seen", "")
        try:
            first_seen = datetime.fromisoformat(first_seen_str)
            age_days = (now - first_seen).total_seconds() / 86400
        except (ValueError, TypeError):
            age_days = 0

        if age_days > max_age:
            continue

        total_score = entry.get("total_score", 0.0)
        max_s = entry.get("max_score", 0.0)
        q_hashes = entry.get("query_hashes", [])
        concept_tags = entry.get("concept_tags", [])

        freq = math.log1p(signal_count) / math.log1p(10)
        relevance = (total_score / signal_count) if signal_count > 0 else 0
        diversity = max(len(q_hashes), len(seen_days)) / 5.0
        # [R2-M2] 使用统一的Ebbinghaus函数计算recency
        # 原实现仅用纯half_life，无access_boost/importance，与memory_tool.py不一致
        # 信号条目没有access_count/importance元数据，使用默认值（0次访问，0.5重要性）
        # 这样当信号被promote为记忆条目后，两者的衰减行为保持一致
        recency = ebbinghaus_retention(age_days=age_days, half_life_days=half_life)

        spacing = 0.0
        span = 0.0
        if len(seen_days) >= 2:
            try:
                day_offsets = [(datetime.fromisoformat(d) - datetime.fromisoformat(seen_days[0])).days for d in seen_days]
                gaps = [day_offsets[i+1] - day_offsets[i] for i in range(len(day_offsets)-1)]
                avg_gap = sum(gaps) / len(gaps) if gaps else 0
                spacing = min(1.0, avg_gap / 7.0)
                span = min(1.0, (day_offsets[-1] - day_offsets[0]) / 30.0)
            except (ValueError, TypeError):
                pass
        consolidation = 0.55 * spacing + 0.45 * span

        conceptual = len(concept_tags) / 6.0

        composite = (
            W_FREQ * freq
            + W_REL * relevance
            + W_DIV * min(diversity, 1.0)
            + W_REC * recency
            + W_CON * consolidation
            + W_CPT * min(conceptual, 1.0)
        )

        if composite >= min_score:
            candidates.append({
                "key": key,
                "snippet": entry.get("snippet", ""),
                "score": round(composite, 4),
                "signal_count": signal_count,
                "seen_days": seen_days,
                "concept_tags": concept_tags,
                "components": {
                    "frequency": round(freq, 3),
                    "relevance": round(relevance, 3),
                    "diversity": round(min(diversity, 1.0), 3),
                    "recency": round(recency, 3),
                    "consolidation": round(consolidation, 3),
                    "conceptual": round(min(conceptual, 1.0), 3),
                },
            })

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates


def _extract_themes(candidates: List[Dict], min_strength: float = 0.75) -> List[Dict]:
    """REM phase: extract recurring themes across scored candidates.

    Groups candidates by shared concept tags, computes pattern strength
    as the fraction of candidates containing that tag.
    """
    if not candidates:
        return []

    tag_counts = Counter()
    for c in candidates:
        for tag in c.get("concept_tags", []):
            tag_counts[tag] += 1

    total = len(candidates)
    themes = []
    for tag, count in tag_counts.most_common(10):
        strength = min(1.0, (count / total) * 2)
        if strength >= min_strength:
            themes.append({
                "theme": tag,
                "strength": round(strength, 3),
                "occurrences": count,
            })

    return themes


def _deduplicate_candidates(candidates: List[Dict], threshold: float = 0.88) -> List[Dict]:
    """Remove semantically similar candidates using Jaccard similarity."""
    result = []
    for c in candidates:
        is_dup = False
        for r in result:
            if _jaccard_text_similarity(c["snippet"], r["snippet"]) >= threshold:  # [R2-J1] 改用封装函数
                is_dup = True
                break
        if not is_dup:
            result.append(c)
    return result


def _promote_to_memory(
    candidates: List[Dict],
    config: Dict[str, Any],
) -> List[Dict]:
    """Write promoted entries into EXPERIENCES.md using the existing MemoryStore format.

    Uses atomic write to avoid disrupting concurrent sessions. Each promoted
    entry is marked with a comment so re-promotion is idempotent.

    [R2-M1] 修复并发写竞争：eviction操作使用memory_lock保护，
    防止distillation的eviction与主会话的add互相覆盖。
    """
    from tools.memory_tool import MemoryStore, ENTRY_DELIMITER

    max_promotions = config.get("max_promotions_per_run", 8)
    to_promote = candidates[:max_promotions]
    if not to_promote:
        return []

    store = MemoryStore()
    store.load_from_disk()

    promoted = []
    today = _today_str()

    for c in to_promote:
        snippet = c["snippet"]
        existing = store._entries.get("experiences", [])
        is_dup = any(
            _jaccard_text_similarity(snippet, e) >= 0.88  # [R2-J1] 改用封装函数
            for e in existing
        )
        if is_dup:
            continue

        marker = f"[distilled:{c['key']}]"
        if any(marker in e for e in existing):
            continue

        entry_text = f"{snippet} {marker}"
        current_chars = len(ENTRY_DELIMITER.join(existing)) if existing else 0
        new_chars = current_chars + len(ENTRY_DELIMITER) + len(entry_text)

        if new_chars > store._char_limits.get("experiences", 4000):
            # [R2-M1] 使用memory_lock保护eviction操作，防止并发写入覆盖
            # 原实现无锁保护：eviction先读existing，再修改_entries，再save_to_disk
            # 若主会话在eviction读后、save前添加了新条目，eviction的save会覆盖主会话的添加
            # 修复：在锁内reload最新数据，确保eviction基于最新状态操作
            with store.memory_lock("experiences") as acquired:
                if not acquired:
                    logger.warning("[R2-M1] Failed to acquire memory lock for eviction, skipping")
                    continue
                # 锁内reload，获取最新数据
                store._reload_target("experiences")
                existing = store._entries.get("experiences", [])

                # 重新检查重复（reload后数据可能已变化）
                if any(_jaccard_text_similarity(snippet, e) >= 0.88 for e in existing):
                    continue
                if any(marker in e for e in existing):
                    continue

                # 重新计算字符数
                current_chars = len(ENTRY_DELIMITER.join(existing)) if existing else 0
                new_chars = current_chars + len(ENTRY_DELIMITER) + len(entry_text)
                if new_chars <= store._char_limits.get("experiences", 4000):
                    # reload后空间足够，无需eviction，直接跳到add
                    pass
                else:
                    candidates_for_eviction = [(i, e) for i, e in enumerate(existing) if "[distilled:" not in e]
                    if not candidates_for_eviction:
                        candidates_for_eviction = [(i, e) for i, e in enumerate(existing)]

                    # 使用共享常量，避免与 memory_tool.py 中定义不同步（此前缺少 "critical"）
                    _PROTECTED_KEYWORDS = _MEMORY_PROTECTED_KEYWORDS

                    def _eviction_score(entry):
                        content = entry.lower()
                        has_protected = any(kw in content for kw in _PROTECTED_KEYWORDS)
                        if has_protected:
                            return (0, 0)  # 永不驱逐保护条目
                        # 修复：纳入 Ebbinghaus 元数据考量，避免高价值短条目被优先驱逐
                        # 原实现仅按条目长度排序，短的非保护条目总是先被驱逐，
                        # 但一个频繁访问（高 access_count）或高 importance 的短条目
                        # 可能比一个很少被访问的长条目更有价值。
                        # 通过 retention_bonus 降低有效驱逐分数：
                        #   有效长度 = 实际长度 / (1 + retention_bonus)
                        # access_count 越高、importance 越高的条目获得越大的保护
                        entry_hash = store._entry_key(entry)
                        meta = store._meta.get("experiences", {}).get(entry_hash, {})
                        access_count = meta.get("access_count", 0)
                        importance = meta.get("importance", 0.5)
                        retention_bonus = min(access_count * 0.1, 2.0) + importance
                        return (1, len(entry) / (1 + retention_bonus))

                    candidates_for_eviction.sort(key=lambda x: _eviction_score(x[1]))

                    evicted_indices = []
                    for idx, _ in candidates_for_eviction:
                        evicted_indices.append(idx)
                        tentative = [e for i, e in enumerate(store._entries["experiences"]) if i not in evicted_indices]
                        freed_chars = len(ENTRY_DELIMITER.join(tentative)) + len(ENTRY_DELIMITER) + len(entry_text)
                        if freed_chars <= store._char_limits.get("experiences", 4000):
                            break

                    for idx in sorted(evicted_indices, reverse=True):
                        store._entries["experiences"].pop(idx)
                    # [R2-M1] _skip_lock=True：外层memory_lock已持有文件锁，
                    # save_to_disk不需要再获取锁，避免嵌套死锁
                    store.save_to_disk("experiences", _skip_lock=True)

            # [并发保护] add操作也在锁保护范围内，使用_skip_lock=True避免嵌套死锁
            # 原实现：add在锁外执行，若主会话在eviction后、add前写入，
            # add的save_to_disk可能覆盖主会话的写入
            result = store.add("experiences", entry_text, _skip_lock=True)
            if result.get("success"):
                promoted.append(c)
        else:
            # 无需eviction时，add也需要锁保护（与上面eviction路径一致）
            with store.memory_lock("experiences"):
                store._reload_target("experiences")
                # reload后重新检查重复
                existing = store._entries.get("experiences", [])
                if any(_jaccard_text_similarity(snippet, e) >= 0.88 for e in existing):
                    continue
                if any(marker in e for e in existing):
                    continue
                result = store.add("experiences", entry_text, _skip_lock=True)
                if result.get("success"):
                    promoted.append(c)

    return promoted


def _mark_promoted(keys: List[str]) -> None:
    """Mark signals as promoted so they aren't re-promoted in future runs."""
    signals_path = _signals_path()
    with file_lock(str(signals_path)):
        signals = _load_json(signals_path, {"version": 1, "entries": {}})
        entries = signals.get("entries", {})
        now = utc_now_iso()  # 整合: 使用统一时间戳函数 [T1]
        for key in keys:
            if key in entries:
                entries[key]["promoted_at"] = now
        signals["updated_at"] = now
        atomic_json_write(signals_path, signals)  # 整合: 使用统一原子写入 [J1]


def _ingest_session_transcripts(lookback_days: int = 7) -> int:
    """Light phase: scan recent session transcripts for memory signals.

    Reads session entries from the SQLite state database, extracts
    assistant messages with substantial content, and records them
    as signals for distillation scoring.
    """
    try:
        from kunming_state import SessionDB
    except ImportError:
        return 0

    count = 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    cutoff_ts = cutoff.isoformat()

    try:
        db = SessionDB()
        sessions = db.list_sessions_rich(limit=20)
        rows = []
        for s in sessions:
            started = s.get("started_at", "")
            if started and started < cutoff_ts:
                continue
            msgs = db.get_messages(s["id"])
            rows.extend(msgs)
    except Exception as e:
        # [异常日志] 添加日志记录，原实现完全吞掉异常导致蒸馏静默失败无法排查
        logger.warning("Failed to ingest session transcripts: %s", e)
        return 0

    # 修复：用户纠正关键词列表，用于从user消息中筛选纠正信号
    _USER_CORRECTION_KEYWORDS = (
        "wrong", "incorrect", "no,", "fix", "错了", "不对", "修改", "改正",
        "应该是", "不是这样", "搞错了", "違う", "直して",
    )

    for row in rows:
        ts = row.get("timestamp", "")
        content = row.get("content", "")
        role = row.get("role", "")

        if not content:
            continue
        if ts < cutoff_ts:
            continue

        # 修复：同时摄入user消息中包含纠正关键词的内容
        # 原实现仅摄入assistant消息，丢失了用户纠正信号
        if role == "assistant":
            snippet = content.strip()[:280]
            if len(snippet) < 30:
                continue
            record_signal(snippet, source="session", score=0.55, query=f"session:{ts[:10]}")
            count += 1
        elif role == "user":
            # 用户纠正消息是高价值信号，给予更高分数
            content_lower = content.lower()
            if any(kw in content_lower for kw in _USER_CORRECTION_KEYWORDS):
                snippet = content.strip()[:280]
                if len(snippet) < 10:
                    continue
                record_signal(snippet, source="session", score=0.75, query=f"correction:{ts[:10]}")
                count += 1

    return count


def _llm_extract_patterns(candidates: List[Dict], themes: List[Dict]) -> List[Dict]:
    """REM phase with LLM: extract deeper patterns from candidates and themes.

    Uses auxiliary_client to call a lightweight LLM for pattern extraction.
    Falls back to heuristic-only if LLM is unavailable.
    """
    if not candidates and not themes:
        return []

    try:
        from agent.auxiliary_client import call_llm
    except ImportError:
        return []

    snippets = [c["snippet"][:120] for c in candidates[:10]]
    theme_str = ", ".join(t["theme"] for t in themes[:5]) if themes else "none"

    prompt = (
        "Analyze these memory entries and extract 1-3 reusable rules or patterns.\n"
        "Each rule should be a concise, actionable insight.\n"
        # 修复：添加多语言输出指令，确保中文/日文记忆提取效果
        "Output rules in the same language as the input entries.\n\n"
        f"Themes found: {theme_str}\n\n"
        f"Entries:\n" + "\n".join(f"- {s}" for s in snippets) + "\n\n"
        "Output format: one rule per line, no numbering, no explanation. "
        "If no clear pattern emerges, output nothing."
    )

    try:
        # [H1修复] call_llm返回OpenAI SDK response对象，不是字符串
        # 原代码对response对象调.strip()会AttributeError，被外层except捕获后静默失败
        # 使用extract_content_or_reasoning正确提取文本内容
        from agent.auxiliary_client import extract_content_or_reasoning
        response = call_llm(messages=[{"role": "user", "content": prompt}], max_tokens=200, temperature=0.3)
        content = extract_content_or_reasoning(response)
        if not content or not content.strip():
            return []
        rules = [r.strip() for r in content.strip().split("\n") if r.strip() and len(r.strip()) > 10]
        return [{"rule": r, "source": "llm_rem"} for r in rules[:3]]
    except Exception as e:
        logger.debug("LLM-assisted REM failed: %s", e)
        return []


def _write_models_to_store(rules: List[Dict]) -> int:
    """Write LLM-extracted rules to the MODELS.md layer.

    [并发保护+去重] 使用memory_lock保护写入，并用Jaccard相似度去重。
    原实现：无锁保护且无去重，若蒸馏与错误提升同时运行会互相覆盖，
    且LLM可能提取与已有规则重复的内容导致MODELS.md膨胀。
    修复：在锁内reload+去重检查+add(_skip_lock=True)，确保原子性和唯一性。
    """
    if not rules:
        return 0
    from tools.memory_tool import MemoryStore
    store = MemoryStore()
    store.load_from_disk()
    written = 0
    # [并发保护] 整个写入操作在锁保护范围内，防止与错误提升的并发写入互相覆盖
    with store.memory_lock("models"):
        store._reload_target("models")
        for r in rules:
            rule_text = f"[model] {r['rule']}"
            # [去重] 检查是否与已有规则高度相似，避免MODELS.md膨胀
            existing = store._entries.get("models", [])
            is_dup = any(_jaccard_text_similarity(rule_text, e) > 0.7 for e in existing)
            if is_dup:
                logger.debug("Skipping duplicate model rule: %s", rule_text[:60])
                continue
            result = store.add("models", rule_text, _skip_lock=True)
            if result.get("success"):
                written += 1
    return written


def _run_ebbinghaus_decay() -> Dict[str, int]:
    """Run Ebbinghaus decay on all memory targets.

    [R2-M1] 修复并发写竞争：每个target的decay操作使用memory_lock保护，
    在锁内reload最新数据后再执行decay，防止与主会话的并发写入互相覆盖。
    原实现：load_from_disk()后直接decay_memories()，load和decay之间无锁保护，
    若主会话在load后、decay前添加了新条目，decay的save_to_disk会覆盖主会话的添加。
    """
    from tools.memory_tool import MemoryStore
    store = MemoryStore()
    store.load_from_disk()
    results = {}
    for target in ("facts", "experiences", "models"):
        # [R2-M1] 每个target独立加锁，避免长时间持有全局锁
        with store.memory_lock(target) as acquired:
            if not acquired:
                logger.warning("[R2-M1] Failed to acquire memory lock for decay on %s, skipping", target)
                continue
            # 锁内reload，确保基于最新数据执行衰减
            store._reload_target(target)
            # _skip_lock=True：外层memory_lock已持有文件锁，decay_memories内部的
            # save_to_disk不需要再获取锁，避免嵌套死锁
            removed = store.decay_memories(target, _skip_lock=True)
            if removed > 0:
                results[target] = removed
    return results


def run_distillation(config: Optional[Dict[str, Any]] = None, verbose: bool = False) -> Dict[str, Any]:
    """Execute a full distillation cycle: Light → REM → Deep → Decay.

    Light: ingest recent session transcripts as signals.
    REM:   extract recurring themes from scored candidates (with optional LLM).
    Deep:  score candidates, promote high-confidence entries to EXPERIENCES.md.
    Decay: run Ebbinghaus forgetting curve to prune stale memories.

    Returns a summary dict with statistics and any themes discovered.
    """
    if config is None:
        config = _DISTILL_DEFAULT_CONFIG.copy()

    if not config.get("enabled", True):
        return {"status": "disabled", "message": "Memory distillation is not enabled."}

    # [蒸馏并发保护] 使用文件锁防止多个cron实例同时运行蒸馏
    # 原理: 蒸馏涉及读取-评分-写入操作，并发执行会导致:
    # 1. 重复评分相同的候选条目 2. 并发写入EXPERIENCES.md导致数据丢失
    # 使用短超时非阻塞锁获取，如果锁已被持有则跳过本次运行
    # timeout=0.5: 尝试获取锁最多0.5秒（至少一次尝试），避免timeout=0时while循环不执行
    distill_lock_path = str(get_kunming_home() / "memories" / ".distillation.lock")
    with file_lock(distill_lock_path, timeout=0.5) as acquired:
        if not acquired:
            logger.info("Distillation already running, skipping this cycle")
            return {"status": "skipped", "message": "Another distillation is already running."}

        start = time.monotonic()
        result = {
            "status": "ok",
            "light": {"signals_ingested": 0},
            "rem": {"themes": [], "llm_rules": []},
            "deep": {"candidates_scored": 0, "promoted": 0, "promotions": []},
            "decay": {},
        }

        _distill_dir().mkdir(parents=True, exist_ok=True)

        lookback = config.get("lookback_days", 7)
        ingested = _ingest_session_transcripts(lookback_days=lookback)
        result["light"]["signals_ingested"] = ingested

        signals_path = _signals_path()
        signals = _load_json(signals_path, {"version": 1, "entries": {}})
        entries = signals.get("entries", {})

        if not entries:
            result["status"] = "no_signals"
            return result

        candidates = _score_candidates(entries, config)
        result["deep"]["candidates_scored"] = len(candidates)

        themes = _extract_themes(candidates)
        result["rem"]["themes"] = themes

        if config.get("llm_assisted_rem", True):
            llm_rules = _llm_extract_patterns(candidates, themes)
            result["rem"]["llm_rules"] = llm_rules
            if llm_rules:
                written = _write_models_to_store(llm_rules)
                result["rem"]["models_written"] = written

        candidates = _deduplicate_candidates(candidates)

        promoted = _promote_to_memory(candidates, config)
        result["deep"]["promoted"] = len(promoted)
        result["deep"]["promotions"] = [
            {"snippet": p["snippet"][:80], "score": p["score"]}
            for p in promoted
        ]

        if promoted:
            _mark_promoted([p["key"] for p in promoted])

        if config.get("decay_on_distill", True):
            decay_results = _run_ebbinghaus_decay()
            result["decay"] = decay_results

        state_path = _state_path()
        with file_lock(str(state_path)):
            state = _load_json(state_path, {"version": 1, "runs": []})
            runs = state.setdefault("runs", [])
            runs.append({
                "timestamp": utc_now_iso(),  # 整合: 使用统一时间戳函数 [T1]
                "duration_ms": int((time.monotonic() - start) * 1000),
                "signals_count": len(entries),
                "candidates_scored": len(candidates),
                "promoted": len(promoted),
                "themes_found": len(themes),
            })
            runs = runs[-50:]
            state["runs"] = runs
            atomic_json_write(state_path, state)  # 整合: 使用统一原子写入 [J1]

        if verbose:
            logger.info(
                "Distillation complete: %d signals, %d candidates, %d promoted, %d themes",
                len(entries), len(candidates), len(promoted), len(themes),
            )

        return result


def get_distillation_status() -> Dict[str, Any]:
    """Return current distillation state for status display."""
    state_path = _state_path()
    state = _load_json(state_path, {"version": 1, "runs": []})

    signals_path = _signals_path()
    signals = _load_json(signals_path, {"version": 1, "entries": {}})
    entries = signals.get("entries", {})

    total_signals = len(entries)
    promoted_count = sum(1 for e in entries.values() if e.get("promoted_at"))
    active_count = total_signals - promoted_count

    last_run = state.get("runs", [{}])[-1] if state.get("runs") else {}

    return {
        "total_signals": total_signals,
        "active_signals": active_count,
        "promoted_signals": promoted_count,
        "last_run": last_run.get("timestamp", "never"),
        "last_promoted_count": last_run.get("promoted", 0),
    }
