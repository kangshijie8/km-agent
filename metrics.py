"""
Runtime metrics collection for the agent system.

Collects token usage, tool call statistics, latency, and cost data.
Uses async batch writes to SQLite for minimal performance impact.
"""

import json
import logging
import os
import sqlite3
import threading
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DB_LOCK = threading.Lock()
_writer_thread: Optional[threading.Thread] = None
_write_queue: list = []
_shutdown_event = threading.Event()
_FLUSH_INTERVAL = 2.0
_FLUSH_BATCH_SIZE = 10
_db_path: Optional[Path] = None


@dataclass
class ToolCallRecord:
    tool_name: str
    success: bool
    latency_ms: float
    error_type: Optional[str] = None


@dataclass
class LLMCallRecord:
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    latency_ms: float = 0.0
    estimated_cost_usd: float = 0.0
    stop_reason: Optional[str] = None


@dataclass
class SessionSummary:
    session_id: str
    platform: str = ""
    model: str = ""
    provider: str = ""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_write_tokens: int = 0
    total_reasoning_tokens: int = 0
    total_api_calls: int = 0
    total_tool_calls: int = 0
    total_tool_errors: int = 0
    total_estimated_cost_usd: float = 0.0
    total_duration_seconds: float = 0.0
    started_at: Optional[str] = None
    ended_at: Optional[str] = None


class MetricsCollector:
    """Thread-safe metrics collector with async SQLite persistence."""

    _instance: Optional["MetricsCollector"] = None
    _init_lock = threading.Lock()

    def __init__(self, db_path: Optional[Path] = None):
        self._lock = threading.Lock()
        self._current_session: Optional[SessionSummary] = None
        self._tool_calls: List[ToolCallRecord] = []
        self._llm_calls: List[LLMCallRecord] = []
        self._tool_error_counts: Dict[str, int] = defaultdict(int)
        self._tool_call_counts: Dict[str, int] = defaultdict(int)
        self._tool_latency_sums: Dict[str, float] = defaultdict(float)
        self._db_path = db_path
        self._started = False

    @classmethod
    def get_instance(cls) -> "MetricsCollector":
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        with cls._init_lock:
            if cls._instance is not None:
                cls._instance.shutdown()
            cls._instance = None

    def start_session(self, session_id: str, model: str = "", provider: str = "", platform: str = ""):
        with self._lock:
            if self._current_session is not None:
                self._flush_session()
            self._current_session = SessionSummary(
                session_id=session_id,
                model=model,
                provider=provider,
                platform=platform,
                started_at=_utc_now_iso(),
            )
            self._tool_calls.clear()
            self._llm_calls.clear()
            self._tool_error_counts.clear()
            self._tool_call_counts.clear()
            self._tool_latency_sums.clear()
            self._started = True
            _ensure_writer_running(self._db_path)

    def record_llm_call(self, record: LLMCallRecord):
        with self._lock:
            self._llm_calls.append(record)
            if self._current_session is not None:
                self._current_session.total_input_tokens += record.input_tokens
                self._current_session.total_output_tokens += record.output_tokens
                self._current_session.total_cache_read_tokens += record.cache_read_tokens
                self._current_session.total_cache_write_tokens += record.cache_write_tokens
                self._current_session.total_reasoning_tokens += record.reasoning_tokens
                self._current_session.total_api_calls += 1
                self._current_session.total_estimated_cost_usd += record.estimated_cost_usd

    def record_tool_call(self, record: ToolCallRecord):
        with self._lock:
            self._tool_calls.append(record)
            self._tool_call_counts[record.tool_name] += 1
            self._tool_latency_sums[record.tool_name] += record.latency_ms
            if not record.success:
                self._tool_error_counts[record.tool_name] += 1
            if self._current_session is not None:
                self._current_session.total_tool_calls += 1
                if not record.success:
                    self._current_session.total_tool_errors += 1

    def end_session(self):
        with self._lock:
            if self._current_session is not None:
                self._current_session.ended_at = _utc_now_iso()
                self._flush_session()
                self._current_session = None

    def get_session_stats(self) -> Optional[SessionSummary]:
        with self._lock:
            if self._current_session is None:
                return None
            return SessionSummary(**asdict(self._current_session))

    def get_tool_stats(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            result = {}
            for name in self._tool_call_counts:
                result[name] = {
                    "calls": self._tool_call_counts[name],
                    "errors": self._tool_error_counts.get(name, 0),
                    "avg_latency_ms": round(
                        self._tool_latency_sums[name] / max(self._tool_call_counts[name], 1), 1
                    ),
                    "error_rate": round(
                        self._tool_error_counts.get(name, 0) / max(self._tool_call_counts[name], 1), 3
                    ),
                }
            return result

    def _flush_session(self):
        if self._current_session is None:
            return
        summary = asdict(self._current_session)
        summary["tool_stats"] = self.get_tool_stats()
        _enqueue_write("session", summary)

    def shutdown(self):
        self.end_session()
        _signal_shutdown()


def _utc_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _get_db_path() -> Path:
    global _db_path
    if _db_path is not None:
        return _db_path
    from kunming_cli.config import get_kunming_home
    _db_path = get_kunming_home() / "metrics.db"
    return _db_path


def _init_db(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS session_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            platform TEXT DEFAULT '',
            model TEXT DEFAULT '',
            provider TEXT DEFAULT '',
            total_input_tokens INTEGER DEFAULT 0,
            total_output_tokens INTEGER DEFAULT 0,
            total_cache_read_tokens INTEGER DEFAULT 0,
            total_cache_write_tokens INTEGER DEFAULT 0,
            total_reasoning_tokens INTEGER DEFAULT 0,
            total_api_calls INTEGER DEFAULT 0,
            total_tool_calls INTEGER DEFAULT 0,
            total_tool_errors INTEGER DEFAULT 0,
            total_estimated_cost_usd REAL DEFAULT 0.0,
            total_duration_seconds REAL DEFAULT 0.0,
            tool_stats TEXT DEFAULT '{}',
            started_at TEXT,
            ended_at TEXT,
            written_at TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_session_started ON session_metrics(started_at);
        CREATE INDEX IF NOT EXISTS idx_session_id ON session_metrics(session_id);
    """)
    conn.commit()
    conn.close()


def _enqueue_write(record_type: str, data: dict):
    global _write_queue
    _write_queue.append((record_type, data, time.time()))


def _ensure_writer_running(db_path: Optional[Path] = None):
    global _writer_thread
    if _writer_thread is not None and _writer_thread.is_alive():
        return
    if db_path is None:
        db_path = _get_db_path()
    _shutdown_event.clear()
    _writer_thread = threading.Thread(
        target=_writer_loop,
        args=(db_path,),
        daemon=True,
        name="metrics-writer",
    )
    _writer_thread.start()


def _writer_loop(db_path: Path):
    _init_db(db_path)
    while not _shutdown_event.is_set():
        _shutdown_event.wait(_FLUSH_INTERVAL)
        _flush_queue(db_path)
    _flush_queue(db_path)


def _flush_queue(db_path: Path):
    global _write_queue
    with _DB_LOCK:
        if not _write_queue:
            return
        batch = _write_queue[:_FLUSH_BATCH_SIZE]
        _write_queue = _write_queue[_FLUSH_BATCH_SIZE:]
    try:
        conn = sqlite3.connect(str(db_path))
        for record_type, data, _ in batch:
            if record_type == "session":
                _write_session(conn, data)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug(f"Metrics write failed: {e}")


def _write_session(conn, data: dict):
    tool_stats = data.pop("tool_stats", "{}")
    if isinstance(tool_stats, dict):
        tool_stats = json.dumps(tool_stats)
    duration = 0.0
    if data.get("started_at") and data.get("ended_at"):
        try:
            from datetime import datetime
            s = datetime.fromisoformat(data["started_at"])
            e = datetime.fromisoformat(data["ended_at"])
            duration = (e - s).total_seconds()
        except Exception:
            pass
    data["total_duration_seconds"] = duration
    data["tool_stats"] = tool_stats
    data["written_at"] = _utc_now_iso()
    cols = [
        "session_id", "platform", "model", "provider",
        "total_input_tokens", "total_output_tokens",
        "total_cache_read_tokens", "total_cache_write_tokens",
        "total_reasoning_tokens", "total_api_calls",
        "total_tool_calls", "total_tool_errors",
        "total_estimated_cost_usd", "total_duration_seconds",
        "tool_stats", "started_at", "ended_at", "written_at",
    ]
    vals = [data.get(c, "") for c in cols]
    placeholders = ",".join("?" * len(cols))
    conn.execute(
        f"INSERT INTO session_metrics ({','.join(cols)}) VALUES ({placeholders})",
        vals,
    )


def _signal_shutdown():
    _shutdown_event.set()


def query_daily_summary(days: int = 7) -> List[Dict[str, Any]]:
    db_path = _get_db_path()
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT
                date(started_at) as day,
                COUNT(*) as session_count,
                SUM(total_input_tokens) as input_tokens,
                SUM(total_output_tokens) as output_tokens,
                SUM(total_cache_read_tokens) as cache_read_tokens,
                SUM(total_cache_write_tokens) as cache_write_tokens,
                SUM(total_api_calls) as api_calls,
                SUM(total_tool_calls) as tool_calls,
                SUM(total_tool_errors) as tool_errors,
                ROUND(SUM(total_estimated_cost_usd), 4) as cost_usd,
                ROUND(AVG(total_duration_seconds), 1) as avg_duration_s
            FROM session_metrics
            WHERE started_at >= datetime('now', ? || ' days')
            GROUP BY date(started_at)
            ORDER BY day DESC
        """, (f"-{days}",)).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.debug(f"Metrics query failed: {e}")
        return []


def query_model_breakdown(days: int = 7) -> List[Dict[str, Any]]:
    db_path = _get_db_path()
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT
                model,
                provider,
                COUNT(*) as session_count,
                SUM(total_input_tokens) as input_tokens,
                SUM(total_output_tokens) as output_tokens,
                SUM(total_api_calls) as api_calls,
                ROUND(SUM(total_estimated_cost_usd), 4) as cost_usd
            FROM session_metrics
            WHERE started_at >= datetime('now', ? || ' days')
            GROUP BY model, provider
            ORDER BY cost_usd DESC
        """, (f"-{days}",)).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.debug(f"Metrics query failed: {e}")
        return []


def format_stats_text(days: int = 7) -> str:
    daily = query_daily_summary(days)
    models = query_model_breakdown(days)
    if not daily and not models:
        return "No metrics data available yet."

    lines = [f"=== Metrics (last {days} days) ===", ""]

    if daily:
        lines.append("Daily Summary:")
        lines.append(f"  {'Date':<12} {'Sessions':>8} {'In Tokens':>12} {'Out Tokens':>12} {'API Calls':>10} {'Cost USD':>10}")
        lines.append(f"  {'-'*12} {'-'*8} {'-'*12} {'-'*12} {'-'*10} {'-'*10}")
        for d in daily:
            lines.append(
                f"  {d.get('day','?'):<12} {d.get('session_count',0):>8} "
                f"{d.get('input_tokens',0):>12,} {d.get('output_tokens',0):>12,} "
                f"{d.get('api_calls',0):>10} {d.get('cost_usd',0):>10.4f}"
            )

    if models:
        lines.append("")
        lines.append("By Model:")
        for m in models:
            lines.append(
                f"  {m.get('model','?')} ({m.get('provider','?')}): "
                f"{m.get('session_count',0)} sessions, "
                f"{m.get('input_tokens',0):,}+{m.get('output_tokens',0):,} tokens, "
                f"${m.get('cost_usd',0):.4f}"
            )

    return "\n".join(lines)
