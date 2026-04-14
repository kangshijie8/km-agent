#!/usr/bin/env python3
"""
Usage Analytics & Telemetry Tool Module

Tracks all tool invocations, session activity, and user behavior patterns.
Provides data-driven insights for product iteration and monetization decisions.

All data stored locally in SQLite. No external analytics services needed.
Privacy-first: nothing leaves the machine unless explicitly exported.

Tools:
- usage_record: Log a tool invocation event (called automatically or manually)
- usage_stats: Get aggregated usage statistics
- usage_trends: Analyze usage trends over time (daily/weekly/monthly)
- usage_export: Export anonymized usage data for analysis
"""

import json
import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from collections import Counter, defaultdict

logger = logging.getLogger(__name__)

from tools.registry import registry

_DB_LOCK = threading.Lock()


def _get_analytics_db_path() -> str:
    from kunming_constants import get_kunming_dir
    return str(get_kunming_dir("analytics.db", "analytics"))


def _get_conn(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or _get_analytics_db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tool_invocations (
            id              TEXT PRIMARY KEY,
            tool_name       TEXT NOT NULL,
            toolset         TEXT NOT NULL DEFAULT '',
            session_id      TEXT NOT NULL DEFAULT '',
            success         INTEGER NOT NULL DEFAULT 1,
            duration_ms     INTEGER NOT NULL DEFAULT 0,
            input_tokens    INTEGER NOT NULL DEFAULT 0,
            output_tokens   INTEGER NOT NULL DEFAULT 0,
            error_type      TEXT NOT NULL DEFAULT '',
            timestamp       TEXT NOT NULL,
            metadata_json   TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_ti_tool   ON tool_invocations(tool_name);
        CREATE INDEX IF NOT EXISTS idx_ti_time   ON tool_invocations(timestamp);
        CREATE INDEX IF NOT EXISTS idx_ti_session ON tool_invocations(session_id);
        CREATE INDEX IF NOT EXISTS idx_ti_set    ON tool_invocations(toolset);

        CREATE TABLE IF NOT EXISTS daily_stats (
            date            TEXT PRIMARY KEY,
            total_calls     INTEGER NOT NULL DEFAULT 0,
            unique_tools    INTEGER NOT NULL DEFAULT 0,
            unique_sessions INTEGER NOT NULL DEFAULT 0,
            success_count   INTEGER NOT NULL DEFAULT 0,
            error_count     INTEGER NOT NULL DEFAULT 0,
            total_duration_ms INTEGER NOT NULL DEFAULT 0,
            top_tool        TEXT NOT NULL DEFAULT '',
            top_tool_count  INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS session_summaries (
            session_id      TEXT PRIMARY KEY,
            start_time      TEXT NOT NULL,
            end_time        TEXT NOT NULL DEFAULT '',
            total_calls     INTEGER NOT NULL DEFAULT 0,
            unique_tools    INTEGER NOT NULL DEFAULT 0,
            primary_domain  TEXT NOT NULL DEFAULT '',
            outcome         TEXT NOT NULL DEFAULT ''
        );
    """)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ===========================================================================
# Tool 1: usage_record - Record a tool invocation event
# ===========================================================================

def _usage_record_handler(args: Dict[str, Any], **kwargs) -> str:
    tool_name = args.get("tool_name", "")
    toolset = args.get("toolset", "")
    session_id = args.get("session_id", kwargs.get("task_id", ""))
    success = int(args.get("success", True))
    duration_ms = int(args.get("duration_ms", 0))
    input_tokens = int(args.get("input_tokens", 0))
    output_tokens = int(args.get("output_tokens", 0))
    error_type = args.get("error_type", "")
    metadata = args.get("metadata", {})

    if not tool_name:
        return json.dumps({"success": False, "error": "tool_name is required"})

    inv_id = f"inv_{uuid.uuid4().hex[:12]}"
    meta_json = json.dumps(metadata, ensure_ascii=False) if isinstance(metadata, dict) else str(metadata)

    with _DB_LOCK:
        conn = _get_conn()
        try:
            _init_db(conn)
            now = _now_iso()
            today = _today_str()

            conn.execute(
                """INSERT INTO tool_invocations
                   (id, tool_name, toolset, session_id, success, duration_ms,
                    input_tokens, output_tokens, error_type, timestamp, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (inv_id, tool_name, toolset, session_id, success, duration_ms,
                 input_tokens, output_tokens, error_type, now, meta_json),
            )

            existing_day = conn.execute(
                "SELECT total_calls FROM daily_stats WHERE date=?", (today,)
            ).fetchone()

            if existing_day:
                conn.execute(
                    """UPDATE daily_stats SET total_calls=total_calls+1,
                       success_count=success_count+?, error_count=error_count+?,
                       total_duration_ms=total_duration_ms+?
                       WHERE date=?""",
                    (success, 1 - success, duration_ms, today),
                )
            else:
                conn.execute(
                    "INSERT INTO daily_stats (date,total_calls,success_count,error_count,total_duration_ms,top_tool) VALUES (?,?,?,?,?,?)",
                    (today, 1, success, 1 - success, duration_ms, tool_name),
                )

            conn.commit()

            return json.dumps({
                "success": True,
                "invocation_id": inv_id,
                "tool_name": tool_name,
                "timestamp": now,
            })
        except Exception as e:
            conn.rollback()
            logger.warning("Failed to record usage: %s", e)
            return json.dumps({"success": False, "error": str(e)})
        finally:
            conn.close()


# ===========================================================================
# Tool 2: usage_stats - Get aggregated statistics
# ===========================================================================

def _usage_stats_handler(args: Dict[str, Any], **kwargs) -> str:
    days = min(args.get("days", 7), 365)
    group_by = args.get("group_by", "day")

    with _DB_LOCK:
        conn = _get_conn()
        try:
            _init_db(conn)
            since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

            total_calls = conn.execute(
                "SELECT COUNT(*) as c FROM tool_invocations WHERE timestamp >= ?", (since,)
            ).fetchone()["c"]

            success_calls = conn.execute(
                "SELECT COUNT(*) as c FROM tool_invocations WHERE timestamp >= ? AND success=1", (since,)
            ).fetchone()["c"]

            unique_tools_raw = conn.execute(
                "SELECT tool_name, COUNT(*) as cnt FROM tool_invocations WHERE timestamp >= ? GROUP BY tool_name ORDER BY cnt DESC",
                (since,),
            ).fetchall()

            toolset_breakdown = conn.execute(
                "SELECT toolset, COUNT(*) as cnt FROM tool_invocations WHERE timestamp >= ? GROUP BY toolset ORDER BY cnt DESC",
                (since,),
            ).fetchall()

            daily_trend = conn.execute(
                "SELECT date, total_calls, success_count, error_count, unique_tools, top_tool FROM daily_stats WHERE date >= ? ORDER BY date",
                (_today_str_from_days(days),),
            ).fetchall()

            total_dur = conn.execute(
                "SELECT COALESCE(SUM(duration_ms), 0) as d FROM tool_invocations WHERE timestamp >= ?", (since,)
            ).fetchone()["d"]

            avg_dur = total_dur / max(1, total_calls)

            active_sessions = conn.execute(
                "SELECT COUNT(DISTINCT session_id) as c FROM tool_invocations WHERE timestamp >= ?", (since,)
            ).fetchone()["c"]

            errors = conn.execute(
                "SELECT error_type, COUNT(*) as cnt FROM tool_invocations WHERE timestamp >= ? AND success=0 GROUP BY error_type ORDER BY cnt DESC LIMIT 10",
                (since,),
            ).fetchall()

            peak_hour_raw = conn.execute(
                "SELECT strftime('%H', timestamp) as hour, COUNT(*) as cnt FROM tool_invocations WHERE timestamp >= ? GROUP BY hour ORDER BY cnt DESC LIMIT 5",
                (since,),
            ).fetchall()

            return json.dumps({
                "success": True,
                "period_days": days,
                "summary": {
                    "total_invocations": total_calls,
                    "success_rate": round(success_calls / max(1, total_calls) * 100, 1),
                    "unique_tools_used": len(unique_tools_raw),
                    "active_sessions": active_sessions,
                    "avg_duration_ms": round(avg_dur, 0),
                    "total_duration_min": round(total_dur / 60000, 1),
                },
                "top_tools": [{"name": r["tool_name"], "calls": r["cnt"]} for r in unique_tools_raw[:15]],
                "by_toolset": [{"toolset": r["toolset"] or "core", "calls": r["cnt"]} for r in toolset_breakdown],
                "daily_trend": [{
                    "date": r["date"], "calls": r["total_calls"],
                    "successes": r["success_count"], "errors": r["error_count"],
                    "unique_tools": r["unique_tools"], "top_tool": r["top_tool"],
                } for r in daily_trend],
                "top_errors": [{"type": r["error_type"] or "unknown", "count": r["cnt"]} for r in errors[:10]],
                "peak_hours": [{"hour": r["hour"], "calls": r["cnt"]} for r in peak_hour_raw],
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})
        finally:
            conn.close()


def _today_str_from_days(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")


# ===========================================================================
# Tool 3: usage_trends - Trend analysis with insights
# ===========================================================================

def _usage_trends_handler(args: Dict[str, Any], **kwargs) -> str:
    days = min(args.get("days", 30), 365)

    with _DB_LOCK:
        conn = _get_conn()
        try:
            _init_db(conn)
            cutoff = _today_str_from_days(days)

            daily_rows = conn.execute(
                "SELECT * FROM daily_stats WHERE date >= ? ORDER BY date", (cutoff,)
            ).fetchall()

            if not daily_rows:
                return json.dumps({"success": True, "trend": "insufficient_data", "message": "Not enough data yet"})

            first_half = daily_rows[:len(daily_rows)//2]
            second_half = daily_rows[len(daily_rows)//2:]

            avg_first = sum(r["total_calls"] for r in first_half) / max(1, len(first_half))
            avg_second = sum(r["total_calls"] for r in second_half) / max(1, len(second_half))

            trend_direction = "increasing" if avg_second > avg_first * 1.1 else ("decreasing" if avg_second < avg_first * 0.9 else "stable")
            growth_pct = round((avg_second - avg_first) / max(1, avg_first) * 100, 1)

            best_day = max(daily_rows, key=lambda r: r["total_calls"])
            worst_day = min(daily_rows, key=lambda r: r["total_calls"])

            tool_growth = {}
            tools_over_time = conn.execute(
                """SELECT tool_name, DATE(timestamp) as day, COUNT(*) as cnt
                   FROM tool_invocations WHERE timestamp >= ?
                   GROUP BY tool_name, day""", (cutoff.replace("-", "-") + " 00:00:00",)
            ).fetchall()
            for r in tools_over_time:
                tn = r["tool_name"]
                if tn not in tool_growth:
                    tool_growth[tn] = []
                tool_growth[tn].append((r["day"], r["cnt"]))

            fastest_growing = []
            for tn, points in tool_growth.items():
                if len(points) >= 2:
                    first_avg = sum(c for _, c in points[:len(points)//2]) / max(1, len(points)//2)
                    second_avg = sum(c for _, c in points[len(points)//2:]) / max(1, len(points) - len(points)//2)
                    if first_avg > 0:
                        growth = round((second_avg - first_avg) / first_avg * 100, 1)
                        if growth > 0:
                            fastest_growing.append({"tool": tn, "growth_pct": growth})
            fastest_growing.sort(key=lambda x: x["growth_pct"], reverse=True)

            dau = [r["total_calls"] for r in daily_rows[-7:]] if len(daily_rows) >= 7 else []
            wau = [r["total_calls"] for r in daily_rows[-28:]] if len(daily_rows) >= 28 else []

            insights = []
            if trend_direction == "increasing":
                insights.append(f"使用量呈上升趋势，近{days//2}天日均调用比前{days//2}天增长{abs(growth_pct)}%")
            elif trend_direction == "decreasing":
                insights.append(f"使用量呈下降趋势，需关注用户留存（下降{abs(growth_pct)}%）")
            else:
                insights.append("使用量保持稳定，用户习惯已形成")
            if best_day["total_calls"] > worst_day["total_calls"] * 3:
                insights.append(f'峰值日({best_day["date"]})是低谷日({worst_day["date"]})的{best_day["total_calls"]//max(1,worst_day["total_calls"])}倍')
            if fastest_growing:
                insights.append(f'增长最快工具: {fastest_growing[0]["tool"]} (+{fastest_growing[0]["growth_pct"]}%)')

            return json.dumps({
                "success": True,
                "period_days": days,
                "trend": {
                    "direction": trend_direction,
                    "growth_percent": growth_pct,
                    "avg_daily_first_half": round(avg_first, 1),
                    "avg_daily_second_half": round(avg_second, 1),
                },
                "best_day": {"date": best_day["date"], "calls": best_day["total_calls"]},
                "worst_day": {"date": worst_day["date"], "calls": worst_day["total_calls"]},
                "fastest_growing_tools": fastest_growing[:10],
                "engagement": {
                    "avg_7day_calls": round(sum(dau)/len(dau), 1) if dau else None,
                    "avg_28day_calls": round(sum(wau)/len(wau), 1) if wau else None,
                    "data_points": len(daily_rows),
                },
                "insights": insights,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})
        finally:
            conn.close()


# ===========================================================================
# Tool 4: usage_export - Export anonymized data
# ===========================================================================

def _usage_export_handler(args: Dict[str, Any], **kwargs) -> str:
    days = min(args.get("days", 30), 365)
    format_type = args.get("format", "json")
    include_sessions = args.get("include_sessions", False)
    anonymize = args.get("anonymize", True)

    with _DB_LOCK:
        conn = _get_conn()
        try:
            _init_db(conn)
            since = _today_str_from_days(days)

            rows = conn.execute(
                "SELECT tool_name, toolset, success, duration_ms, timestamp, error_type FROM tool_invocations WHERE timestamp >= ? ORDER BY timestamp",
                (since.replace("-", "-") + " 00:00:00",),
            ).fetchall()

            export_data = {
                "exported_at": _now_iso(),
                "period_days": days,
                "total_records": len(rows),
                "records": [
                    {
                        "tool": r["tool_name"],
                        "toolset": r["toolset"],
                        "ok": bool(r["success"]),
                        "duration_ms": r["duration_ms"],
                        "time": r["timestamp"],
                        "error": r["error_type"],
                    }
                    for r in rows
                ],
            }

            if include_sessions:
                sessions = conn.execute(
                    "SELECT * FROM session_summaries", ()
                ).fetchall()
                export_data["sessions"] = [
                    {k: s[k] for k in s.keys()} for s in sessions
                ]

            if format_type == "csv":
                lines = ["tool,toolset,success,duration_ms,timestamp,error"]
                for r in rows:
                    lines.append(f'{r["tool_name"]},{r["toolset"] or ""},{r["success"]},{r["duration_ms"]},{r["timestamp"]},{r["error_type"]}')
                csv_content = "\n".join(lines)
                return json.dumps({"success": True, "format": "csv", "record_count": len(rows), "data": csv_content})

            return json.dumps({"success": True, **export_data}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})
        finally:
            conn.close()


# ===========================================================================
# Registration
# ===========================================================================

registry.register(
    name="usage_record",
    toolset="analytics",
    schema={
        "name": "usage_record",
        "description": "Record a tool invocation event for analytics tracking. Logs tool name, success/failure, duration, tokens used. Called automatically by the system or manually.",
        "parameters": {
            "type": "object",
            "properties": {
                "tool_name": {"type": "string", "description": "Name of the tool that was invoked"},
                "toolset": {"type": "string", "description": "Toolset this tool belongs to"},
                "session_id": {"type": "string", "description": "Current session ID (optional)"},
                "success": {"type": "boolean", "description": "Whether the invocation succeeded (default: true)"},
                "duration_ms": {"type": "number", "description": "How long the tool took in milliseconds"},
                "input_tokens": {"type": "number", "description": "Input token count (if applicable)"},
                "output_tokens": {"type": "number", "description": "Output token count (if applicable)"},
                "error_type": {"type": "string", "description": "Error category if failed"},
                "metadata": {"type": "object", "description": "Additional context data"},
            },
            "required": ["tool_name"],
        },
    },
    handler=_usage_record_handler,
)

registry.register(
    name="usage_stats",
    toolset="analytics",
    schema={
        "name": "usage_stats",
        "description": "Get comprehensive usage statistics: total calls, success rate, top tools, hourly distribution, error breakdown, daily trends.",
        "parameters": {
            "type": "object",
            "properties": {
                "days": {"type": "number", "description": "Lookback period in days (default: 7)"},
                "group_by": {"type": "string", "enum": ["day", "week", "tool", "toolset", "session"],
                             "description": "Grouping dimension (default: day)"},
            },
        },
    },
    handler=_usage_stats_handler,
)

registry.register(
    name="usage_trends",
    toolset="analytics",
    schema={
        "name": "usage_trends",
        "description": "Analyze usage trends over time with AI-generated insights. Detects growth/decline patterns, identifies fastest-growing tools, calculates engagement metrics (DAU/WAU).",
        "parameters": {
            "type": "object",
            "properties": {
                "days": {"type": "number", "description": "Analysis period in days (default: 30)"},
            },
        },
    },
    handler=_usage_trends_handler,
)

registry.register(
    name="usage_export",
    toolset="analytics",
    schema={
        "name": "usage_export",
        "description": "Export anonymized usage data for external analysis. Supports JSON and CSV formats.",
        "parameters": {
            "type": "object",
            "properties": {
                "days": {"type": "number", "description": "Export period in days (default: 30)"},
                "format": {"type": "string", "enum": ["json", "csv"], "description": "Output format (default: json)"},
                "include_sessions": {"type": "boolean", "description": "Also include session summaries (default: false)"},
                "anonymize": {"type": "boolean", "description": "Remove PII before export (default: true)"},
            },
        },
    },
    handler=_usage_export_handler,
)
