#!/usr/bin/env python3
"""
Experience Learning Tool Module

Builds on top of the existing MemoryDistillation system to provide:
- Tool-use pattern extraction & storage ("what worked before")
- Experience scoring with user feedback loop
- Successful pattern retrieval at query time
- Cross-session experience accumulation

Architecture:
    User interaction → extract_pattern() → store in experience DB
                    ↓
         Similar query arrives → match_experience() → suggest proven approaches
                    ↓
         User confirms success → reinforce() → boost pattern score
         User rejects/negative → penalize() → lower pattern score

No external API keys needed. Uses SQLite + JSON for local storage.
Works entirely offline after initial setup.
"""

import json
import logging
import os
import re
import sqlite3
import tempfile
import threading
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from tools.registry import registry

_DB_LOCK = threading.Lock()


def _get_exp_db_path() -> str:
    try:
        from kunming_constants import get_kunming_dir
        return str(get_kunming_dir("experience.db", "experience"))
    except ImportError:
        return str(Path(tempfile.gettempdir()) / "kunming_experience.db")


def _get_conn(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or _get_exp_db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS experiences (
            id              TEXT PRIMARY KEY,
            pattern_hash    TEXT UNIQUE,
            query_type      TEXT NOT NULL DEFAULT '',
            query_keywords  TEXT NOT NULL DEFAULT '',
            tool_sequence   TEXT NOT NULL DEFAULT '[]',
            outcome         TEXT NOT NULL DEFAULT 'unknown',
            success_score   REAL NOT NULL DEFAULT 0.5,
            use_count       INTEGER NOT NULL DEFAULT 0,
            positive_count  INTEGER NOT NULL DEFAULT 0,
            negative_count  INTEGER NOT NULL DEFAULT 0,
            context_summary TEXT NOT NULL DEFAULT '',
            domain          TEXT NOT NULL DEFAULT 'general',
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_exp_query   ON experiences(query_type, query_keywords);
        CREATE INDEX IF NOT EXISTS idx_exp_domain   ON experiences(domain);
        CREATE INDEX IF NOT EXISTS idx_exp_score   ON experiences(success_score DESC);
        CREATE INDEX IF NOT EXISTS idx_exp_outcome ON experiences(outcome);

        CREATE TABLE IF NOT EXISTS feedback_events (
            id              TEXT PRIMARY KEY,
            experience_id   TEXT NOT NULL,
            feedback_type   TEXT NOT NULL CHECK(feedback_type IN ('positive','negative','neutral')),
            session_id      TEXT NOT NULL DEFAULT '',
            notes           TEXT NOT NULL DEFAULT '',
            created_at      TEXT NOT NULL,
            FOREIGN KEY (experience_id) REFERENCES experiences(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_fb_exp ON feedback_events(experience_id);
    """)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _simple_hash(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _extract_keywords(text: str, max_kws: int = 10) -> str:
    keywords = []
    en_words = re.findall(r'[a-zA-Z][a-zA-Z0-9_-]*', text.lower())
    keywords.extend(en_words)
    cn_chars = re.findall(r'[\u4e00-\u9fff]', text)
    if len(cn_chars) >= 2:
        for i in range(len(cn_chars) - 1):
            keywords.append(cn_chars[i] + cn_chars[i+1])
    elif len(cn_chars) == 1:
        keywords.append(cn_chars[0])
    stop_words = {"这个", "那个", "可以", "需要", "帮助", "如何", "什么",
                   "the", "and", "for", "with", "that", "this", "from"}
    seen = set()
    result = []
    for k in keywords:
        if k not in seen and k not in stop_words:
            seen.add(k)
            result.append(k)
    return ",".join(result[:max_kws])


from collections import Counter


# ===========================================================================
# Tool 1: experience_record - Record a tool-use pattern as an experience
# ===========================================================================

def _experience_record_handler(args: Dict[str, Any], **kwargs) -> str:
    query = args.get("query", "")
    query_type = args.get("query_type", "general")
    tool_sequence = args.get("tool_sequence", [])
    if isinstance(tool_sequence, str):
        try:
            tool_sequence = json.loads(tool_sequence)
        except (json.JSONDecodeError, TypeError):
            tool_sequence = [t.strip() for t in tool_sequence.split(",") if t.strip()]
    outcome = args.get("outcome", "unknown")
    context_summary = args.get("context_summary", "")
    domain = args.get("domain", "general")

    if not query:
        return json.dumps({"success": False, "error": "query is required"})

    seq_json = json.dumps(tool_sequence, ensure_ascii=False)
    pat_hash = _simple_hash(f"{query_type}:{seq_json}")
    keywords = _extract_keywords(query)

    with _DB_LOCK:
        conn = _get_conn()
        try:
            _init_db(conn)
            now = _now_iso()
            existing = conn.execute(
                "SELECT id, use_count, positive_count, negative_count FROM experiences WHERE pattern_hash=?",
                (pat_hash,),
            ).fetchone()

            if existing:
                new_count = existing["use_count"] + 1
                new_outcome = outcome if outcome != "unknown" else existing["outcome"]
                conn.execute(
                    """UPDATE experiences SET use_count=?, outcome=?, success_score=?,
                       positive_count=?, negative_count=?, context_summary=?, updated_at=?
                       WHERE id=?""",
                    (new_count, new_outcome,
                     _calc_score(new_count, existing["positive_count"], existing["negative_count"]),
                     existing["positive_count"] + (1 if outcome == "success" else 0),
                     existing["negative_count"] + (1 if outcome == "failure" else 0),
                     context_summary or existing["context_summary"],
                     now, existing["id"]),
                )
                exp_id = existing["id"]
                is_new = False
            else:
                exp_id = f"exp_{uuid.uuid4().hex[:12]}"
                init_pos = 1 if outcome == "success" else 0
                init_neg = 1 if outcome == "failure" else 0
                conn.execute(
                    """INSERT INTO experiences
                       (id, pattern_hash, query_type, query_keywords, tool_sequence,
                        outcome, success_score, use_count, positive_count, negative_count,
                        context_summary, domain, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (exp_id, pat_hash, query_type, keywords, seq_json,
                     outcome, _calc_score(1, init_pos, init_neg),
                     1, init_pos, init_neg,
                     context_summary, domain, now, now),
                )
                is_new = True

            conn.commit()
            row = conn.execute(
                "SELECT * FROM experiences WHERE id=?", (exp_id,)
            ).fetchone()
            return json.dumps({
                "success": True,
                "experience_id": exp_id,
                "is_new": is_new,
                "pattern_hash": pat_hash,
                "query_type": query_type,
                "tool_sequence": tool_sequence,
                "outcome": outcome,
                "success_score": round(row["success_score"], 3),
                "use_count": row["use_count"],
                "keywords": keywords,
            }, ensure_ascii=False)
        except Exception as e:
            conn.rollback()
            return json.dumps({"success": False, "error": str(e)})
        finally:
            conn.close()


# ===========================================================================
# Tool 2: experience_search - Find relevant past experiences for current query
# ===========================================================================

def _experience_search_handler(args: Dict[str, Any], **kwargs) -> str:
    query = args.get("query", "")
    query_type = args.get("query_type", "")
    domain = args.get("domain", "")
    limit = min(args.get("limit", 5), 20)
    min_score = args.get("min_score", 0.3)
    outcome_filter = args.get("outcome_filter", "")

    if not query:
        return json.dumps({"success": False, "error": "query is required"})

    keywords = _extract_keywords(query)
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()]

    with _DB_LOCK:
        conn = _get_conn()
        try:
            _init_db(conn)

            where_parts = ["success_score >= ?"]
            params: List[Any] = [min_score]

            if query_type:
                where_parts.append("query_type = ?")
                params.append(query_type)
            if domain:
                where_parts.append("domain = ?")
                params.append(domain)
            if outcome_filter:
                where_parts.append("outcome = ?")
                params.append(outcome_filter)

            if kw_list:
                kw_conditions = " OR ".join(["query_keywords LIKE ?"] * len(kw_list))
                where_parts.append(f"({kw_conditions})")
                params.extend([f"%{kw}%" for kw in kw_list])

            where_sql = " AND ".join(where_parts)
            order = "success_score DESC, use_count DESC, updated_at DESC"

            rows = conn.execute(
                f"SELECT * FROM experiences WHERE {where_sql} ORDER BY {order} LIMIT ?",
                (*params, limit),
            ).fetchall()

            results = []
            for r in rows:
                results.append({
                    "experience_id": r["id"],
                    "query_type": r["query_type"],
                    "tool_sequence": json.loads(r["tool_sequence"]),
                    "outcome": r["outcome"],
                    "success_score": round(r["success_score"], 3),
                    "use_count": r["use_count"],
                    "positive_count": r["positive_count"],
                    "negative_count": r["negative_count"],
                    "context_summary": r["context_summary"],
                    "domain": r["domain"],
                    "keywords": r["query_keywords"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                })

            return json.dumps({
                "success": True,
                "query": query,
                "matched_keywords": kw_list,
                "total_results": len(results),
                "results": results,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})
        finally:
            conn.close()


# ===========================================================================
# Tool 3: experience_feedback - Record user feedback on an experience
# ===========================================================================

def _experience_feedback_handler(args: Dict[str, Any], **kwargs) -> str:
    experience_id = args.get("experience_id", "")
    feedback_type = args.get("feedback_type", "neutral")
    notes = args.get("notes", "")
    session_id = args.get("session_id", "")

    if not experience_id:
        return json.dumps({"success": False, "error": "experience_id is required"})
    if feedback_type not in ("positive", "negative", "neutral"):
        return json.dumps({"success": False, "error": "feedback_type must be positive/negative/neutral"})

    fb_id = f"fb_{uuid.uuid4().hex[:12]}"
    now = _now_iso()

    with _DB_LOCK:
        conn = _get_conn()
        try:
            _init_db(conn)
            conn.execute(
                "INSERT INTO feedback_events (id, experience_id, feedback_type, session_id, notes, created_at) VALUES (?,?,?,?,?,?)",
                (fb_id, experience_id, feedback_type, session_id, notes, now),
            )

            delta_pos = 1 if feedback_type == "positive" else 0
            delta_neg = 1 if feedback_type == "negative" else 0

            conn.execute(
                """UPDATE experiences SET
                   positive_count = positive_count + ?,
                   negative_count = negative_count + ?,
                   use_count = use_count + 1,
                   updated_at = ?,
                   outcome = CASE
                     WHEN ? = 'positive' THEN 'success'
                     WHEN ? = 'failure' THEN outcome
                     ELSE outcome
                   END
                 WHERE id=?""",
                (delta_pos, delta_neg, now,
                 "success" if feedback_type == "positive" else "",
                 "failure" if feedback_type == "negative" else "",
                 experience_id),
            )

            row = conn.execute(
                "SELECT positive_count, negative_count, use_count FROM experiences WHERE id=?",
                (experience_id,),
            ).fetchone()

            new_score = None
            if row:
                new_score = _calc_score(row["use_count"], row["positive_count"], row["negative_count"])
                conn.execute(
                    "UPDATE experiences SET success_score=? WHERE id=?",
                    (new_score, experience_id),
                )

            conn.commit()
            return json.dumps({
                "success": True,
                "feedback_id": fb_id,
                "experience_id": experience_id,
                "feedback_type": feedback_type,
                "new_score": round(new_score, 3) if row else None,
            })
        except Exception as e:
            conn.rollback()
            return json.dumps({"success": False, "error": str(e)})
        finally:
            conn.close()


# ===========================================================================
# Tool 4: experience_stats - Get learning statistics and insights
# ===========================================================================

def _experience_stats_handler(args: Dict[str, Any], **kwargs) -> str:
    domain = args.get("domain", "")
    days = args.get("days", 30)

    with _DB_LOCK:
        conn = _get_conn()
        try:
            _init_db(conn)
            since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

            base_where = "WHERE created_at >= ?"
            bp = [since]
            if domain:
                base_where += " AND domain=?"
                bp.append(domain)

            total = conn.execute(f"SELECT COUNT(*) as c FROM experiences {base_where}", bp).fetchone()["c"]
            successes = conn.execute(f"SELECT COUNT(*) as c FROM experiences {base_where} AND outcome='success'", bp).fetchone()["c"]
            failures = conn.execute(f"SELECT COUNT(*) as c FROM experiences {base_where} AND outcome='failure'", bp).fetchone()["c"]

            top_domains = conn.execute(
                f"SELECT domain, COUNT(*) as cnt FROM experiences {base_where} GROUP BY domain ORDER BY cnt DESC LIMIT 10", bp
            ).fetchall()

            top_patterns = conn.execute(
                f"SELECT query_type, tool_sequence, success_score, use_count, outcome FROM experiences {base_where} ORDER BY success_score DESC LIMIT 10", bp
            ).fetchall()

            top_tools_raw = conn.execute(
                f"SELECT tool_sequence FROM experiences {base_where} AND outcome='success'", bp
            ).fetchall()
            tool_freq = Counter()
            for r in top_tools_raw:
                try:
                    for t in json.loads(r["tool_sequence"]):
                        tool_freq[t] += 1
                except (json.JSONDecodeError, TypeError):
                    pass

            recent_feedback = conn.execute(
                f"SELECT feedback_type, COUNT(*) as cnt FROM feedback_events WHERE created_at >= ? GROUP BY feedback_type",
                (since,),
            ).fetchall()

            avg_score_row = conn.execute(f"SELECT AVG(success_score) as s FROM experiences {base_where}", bp).fetchone()

            return json.dumps({
                "success": True,
                "period_days": days,
                "total_experiences": total,
                "successes": successes,
                "failures": failures,
                "success_rate": round(successes / total * 100, 1) if total > 0 else 0,
                "avg_success_score": round(avg_score_row["s"] or 0, 3),
                "top_domains": [{"domain": r["domain"], "count": r["cnt"]} for r in top_domains],
                "top_patterns": [{
                    "query_type": r["query_type"],
                    "tools": json.loads(r["tool_sequence"]),
                    "score": round(r["success_score"], 3),
                    "uses": r["use_count"],
                    "outcome": r["outcome"],
                } for r in top_patterns],
                "most_successful_tools": tool_freq.most_common(10),
                "feedback_summary": {r["feedback_type"]: r["cnt"] for r in recent_feedback},
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})
        finally:
            conn.close()


# ===========================================================================
# Helper: Bayesian success score calculation
# ===========================================================================

def _calc_score(use_count: int, positives: int, negatives: int) -> float:
    if use_count == 0:
        return 0.5
    alpha = 1 + positives
    beta = 1 + negatives
    raw = alpha / (alpha + beta)
    confidence = min(1.0, use_count / 10.0)
    return round(0.3 + raw * 0.7 * confidence, 4)


# ===========================================================================
# Registration
# ===========================================================================

registry.register(
    name="experience_record",
    toolset="learning",
    schema={
        "name": "experience_record",
        "description": "Record a tool-use pattern as a learned experience. Tracks what tools were used for what type of query and whether it succeeded. Builds the experience database over time.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "User's original request/query text"},
                "query_type": {"type": "string", "description": "Category of query (e.g., 'content_creation', 'code_debug', 'research', 'translation')"},
                "tool_sequence": {"type": "array", "items": {"type": "string"},
                               "description": "Ordered list of tool names used to handle this query"},
                "outcome": {"type": "string", "enum": ["success", "failure", "partial", "unknown"],
                           "description": "Result of this tool-use attempt"},
                "context_summary": {"type": "string", "description": "Brief description of what worked/didn't work"},
                "domain": {"type": "string", "description": "Domain area (e.g., 'media', 'dev', 'productivity')"},
            },
            "required": ["query", "tool_sequence"],
        },
    },
    handler=_experience_record_handler,
)

registry.register(
    name="experience_search",
    toolset="learning",
    schema={
        "name": "experience_search",
        "description": "Search the experience database for similar past queries and their successful tool-use patterns. Helps reuse proven approaches instead of guessing.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Current query to find matching experiences for"},
                "query_type": {"type": "string", "description": "Filter by query type/category (optional)"},
                "domain": {"type": "string", "description": "Filter by domain (optional)"},
                "limit": {"type": "number", "description": "Max results (default: 5)"},
                "min_score": {"type": "number", "description": "Minimum success score threshold (default: 0.3)"},
                "outcome_filter": {"type": "string", "enum": ["success", "failure", "partial"],
                                 "description": "Only return experiences with this outcome (optional)"},
            },
            "required": ["query"],
        },
    },
    handler=_experience_search_handler,
)

registry.register(
    name="experience_feedback",
    toolset="learning",
    schema={
        "name": "experience_feedback",
        "description": "Record user feedback on a past experience. Positive feedback reinforces the pattern, negative reduces its score. This is how the system learns from outcomes.",
        "parameters": {
            "type": "object",
            "properties": {
                "experience_id": {"type": "string", "description": "ID of the experience to give feedback on"},
                "feedback_type": {"type": "string", "enum": ["positive", "negative", "neutral"],
                                  "description": "'positive' = this approach worked well, 'negative' = it didn't work"},
                "notes": {"type": "string", "description": "Optional notes about why it worked/didn't"},
                "session_id": {"type": "string", "description": "Current session ID for tracking"},
            },
            "required": ["experience_id", "feedback_type"],
        },
    },
    handler=_experience_feedback_handler,
)

registry.register(
    name="experience_stats",
    toolset="learning",
    schema={
        "name": "experience_stats",
        "description": "Get statistics about accumulated experiences: success rates, most-used patterns, top domains, learning progress over time.",
        "parameters": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Filter stats by domain (optional)"},
                "days": {"type": "number", "description": "Lookback period in days (default: 30)"},
            },
        },
    },
    handler=_experience_stats_handler,
)
