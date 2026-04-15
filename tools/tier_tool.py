#!/usr/bin/env python3
"""
Tier & Feature Gate Tool Module

Implements free/paid tier system for monetization:
- Feature gating: which features are available in each tier
- Quota management: daily/monthly usage limits per tier
- Tier detection: auto-detect user's current tier from config/license
- Upgrade prompts: generate contextual upgrade messages

Tier structure:
  FREE:     Core tools, 5 sessions/day, basic memory, 50 skills
  CREATOR:  All media tools, unlimited sessions, experience learning, all skills, priority support
  PRO:      Everything + API access + multi-agent + custom models + analytics dashboard

No external license server needed - tier is stored in local config.
"""

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from tools.registry import registry

_DB_LOCK = threading.Lock()


TIER_DEFINITIONS = {
    "free": {
        "name": "免费版",
        "price": 0,
        "description": "基础AI助手功能",
        "daily_sessions": 5,
        "daily_tool_calls": 100,
        "max_skills": 50,
        "max_memory_entries": 500,
        "allowed_toolsets": ["core", "tts", "learning"],
        "blocked_toolsets": ["media", "analytics"],
        "blocked_tools": [],
        "features": [
            "basic_chat", "file_read_write", "web_search", "terminal",
            "edge_tts_voice", "basic_memory", "experience_learning",
            "single_platform", "basic_skills",
        ],
        "upgrade_reasons": ["解锁内容创作工具包", "去除使用次数限制", "获得完整技能库"],
    },
    "creator": {
        "name": "创作者版",
        "price": 99,
        "price_period": "month",
        "description": "面向内容创作者的完整工具集",
        "daily_sessions": -1,
        "daily_tool_calls": 1000,
        "max_skills": 276,
        "max_memory_entries": 10000,
        "allowed_toolsets": ["core", "tts", "media", "learning", "analytics"],
        "blocked_toolsets": [],
        "blocked_tools": [],
        "features": [
            "everything_in_free", "video_assemble", "srt_subtitles", "cover_generation",
            "audio_mixing", "content_pipeline_templates", "experience_learning",
            "usage_analytics", "all_platforms", "all_skills", "priority_queue",
            "custom_skins", "batch_processing",
        ],
        "upgrade_reasons": ["API访问权限", "多Agent协作系统", "高级认知功能"],
    },
    "pro": {
        "name": "专业版",
        "price": 299,
        "price_period": "month",
        "description": "面向团队和高级用户的完整方案",
        "daily_sessions": -1,
        "daily_tool_calls": -1,
        "max_skills": -1,
        "max_memory_entries": -1,
        "allowed_toolsets": [],
        "blocked_toolsets": [],
        "blocked_tools": [],
        "features": [
            "everything_in_creator", "api_server_access", "multi_agent_delegation",
            "mixture_of_agents", "rl_training", "custom_model_routing",
            "advanced_memory_plugins", "team_collaboration", "web_dashboard",
            "priority_support", "unlimited_everything",
        ],
        "upgrade_reasons": [],
    },
}

FEATURE_DESCRIPTIONS = {
    "basic_chat": "基础对话能力，支持多轮上下文",
    "file_read_write": "文件读写、搜索、编辑",
    "web_search": "网络搜索和网页内容提取",
    "terminal": "终端命令执行和后台进程管理",
    "edge_tts_voice": "Edge TTS免费中文语音合成",
    "basic_memory": "基础记忆功能（500条上限）",
    "experience_learning": "经验学习系统（越用越聪明）",
    "single_platform": "单平台消息接入",
    "basic_skills": "50个基础Skills",
    "video_assemble": "视频组装：图片+音频+字幕→MP4",
    "srt_subtitles": "自动时间轴SRT字幕生成",
    "cover_generate": "PIL封面图生成（4种风格）",
    "audio_mixing": "音频混音（语音+BGM）",
    "content_pipeline_templates": "5种爆款内容模板+6平台规格",
    "usage_analytics": "使用统计和行为分析面板",
    "all_platforms": "15+消息平台同时接入",
    "all_skills": "276+全部Skills库",
    "priority_queue": "高峰期优先响应",
    "custom_skins": "自定义UI皮肤主题",
    "batch_processing": "批量任务处理能力",
    "api_server_access": "HTTP API服务端模式",
    "multi_agent_delegation": "子代理任务委派和并行处理",
    "mixture_of_agents": "多模型混合推理",
    "rl_training": "强化学习策略训练",
    "custom_model_routing": "自定义模型路由规则",
    "advanced_memory_plugins": "高级记忆后端插件（Mem0/RetainDB等）",
    "team_collaboration": "多用户团队协作",
    "web_dashboard": "Web管理控制台",
    "priority_support": "优先技术支持通道",
    "unlimited_everything": "无任何限制",
}


def _get_tier_db_path() -> str:
    from kunming_constants import get_kunming_dir
    return str(get_kunming_dir("tier.db", "tier"))


def _get_conn():
    path = _get_tier_db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tier_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS quota_usage (
            id TEXT PRIMARY KEY,
            tier TEXT NOT NULL DEFAULT 'free',
            date TEXT NOT NULL DEFAULT '',
            metric TEXT NOT NULL DEFAULT '',
            count INTEGER NOT NULL DEFAULT 0,
            limit_val INTEGER NOT NULL DEFAULT 0,
            reset_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_quota_date ON quota_usage(date, metric);
    """)


def _get_current_tier() -> str:
    try:
        with _DB_LOCK:
            conn = _get_conn()
            try:
                _init_db(conn)
                row = conn.execute("SELECT value FROM tier_config WHERE key='current_tier'").fetchone()
                if row and row["value"] in TIER_DEFINITIONS:
                    return row["value"]
                conn.execute("INSERT OR IGNORE INTO tier_config (key,value) VALUES ('current_tier','free')")
                conn.commit()
                return "free"
            finally:
                conn.close()
    except Exception:
        return "free"


def _set_tier(tier_name: str) -> bool:
    if tier_name not in TIER_DEFINITIONS:
        return False
    with _DB_LOCK:
        conn = _get_conn()
        try:
            _init_db(conn)
            conn.execute("INSERT OR REPLACE INTO tier_config (key,value) VALUES ('current_tier',?)", (tier_name,))
            conn.commit()
            return True
        finally:
            conn.close()


def _check_quota(metric: str, amount: int = 1) -> Dict[str, Any]:
    tier = _get_current_tier()
    spec = TIER_DEFINITIONS[tier]
    today = datetime.now().strftime("%Y-%m-%d")

    limit_map = {
        "sessions": spec["daily_sessions"],
        "tool_calls": spec["daily_tool_calls"],
    }
    limit_val = limit_map.get(metric, -1)

    # 处理无效或负数的限制值（-1 表示无限制，其他负数视为配置错误）
    if limit_val == -1:
        return {"allowed": True, "used": 0, "limit": -1, "remaining": -1, "tier": tier}
    if limit_val < 0:
        logger.warning("Invalid quota limit for metric '%s': %d (must be -1 or positive)", metric, limit_val)
        # 将负数限制视为无限制，避免意外拒绝服务
        return {"allowed": True, "used": 0, "limit": -1, "remaining": -1, "tier": tier}

    with _DB_LOCK:
        conn = _get_conn()
        try:
            _init_db(conn)
            row = conn.execute(
                "SELECT count FROM quota_usage WHERE date=? AND metric=?", (today, metric)
            ).fetchone()

            current = row["count"] if row else 0
            new_count = current + amount

            if new_count > limit_val:
                return {"allowed": False, "used": current, "limit": limit_val, "remaining": 0, "tier": tier}

            if row:
                conn.execute("UPDATE quota_usage SET count=? WHERE date=? AND metric=?", (new_count, today, metric))
            else:
                qid = f"q_{uuid.uuid4().hex[:8]}"
                conn.execute(
                    "INSERT INTO quota_usage (id,tier,date,metric,count,limit_val,reset_at) VALUES (?,?,?,?,?,?,?)",
                    (qid, tier, today, metric, new_count, limit_val, (datetime.now() + timedelta(days=1)).isoformat()),
                )
            conn.commit()
            return {"allowed": True, "used": new_count, "limit": limit_val, "remaining": limit_val - new_count, "tier": tier}
        finally:
            conn.close()


# ===========================================================================
# Tool 1: tier_check - Check feature availability and quotas
# ===========================================================================

def _tier_check_handler(args: Dict[str, Any], **kwargs) -> str:
    tool_name = args.get("tool_name", "")
    toolset = args.get("toolset", "")
    check_only = args.get("check_only", False)

    tier = _get_current_tier()
    spec = TIER_DEFINITIONS[tier]

    blocked_sets = set(spec.get("blocked_toolsets", []))
    allowed_sets = set(spec.get("allowed_toolsets", []))
    blocked_tools = set(spec.get("blocked_tools", []))

    tool_allowed = True
    block_reason = ""

    if tool_name in blocked_tools:
        tool_allowed = False
        block_reason = f"'{tool_name}' 在当前等级({spec['name']})不可用"
    elif toolset and blocked_sets and toolset in blocked_sets:
        tool_allowed = False
        block_reason = f"'{toolset}' 工具集需要升级到创作者版"
    elif toolset and allowed_sets and toolset not in allowed_sets and allowed_sets:
        pass

    if check_only:
        return json.dumps({
            "success": True,
            "tier": tier,
            "tier_name": spec["name"],
            "tool_allowed": tool_allowed,
            "block_reason": block_reason,
        }, ensure_ascii=False)

    session_quota = _check_quota("sessions", 0)
    calls_quota = _check_quota("tool_calls", 0)

    result = {
        "success": True,
        "current_tier": tier,
        "tier_name": spec["name"],
        "price": spec["price"],
        "price_period": spec.get("price_period", ""),
        "tool_check": {
            "tool_name": tool_name or "(not specified)",
            "toolset": toolset or "(not specified)",
            "allowed": tool_allowed,
            "block_reason": block_reason,
        },
        "quotas": {
            "sessions": session_quota,
            "tool_calls": calls_quota,
        },
        "features": spec["features"],
        "upgrade_reasons": spec.get("upgrade_reasons", []),
        "next_tier": None,
    }

    tiers_list = list(TIER_DEFINITIONS.keys())
    current_idx = tiers_list.index(tier) if tier in tiers_list else 0
    if current_idx < len(tiers_list) - 1:
        next_tier_name = tiers_list[current_idx + 1]
        next_spec = TIER_DEFINITIONS[next_tier_name]
        result["next_tier"] = {
            "name": next_tier_name,
            "display_name": next_spec["name"],
            "price": next_spec["price"],
            "price_period": next_spec.get("price_period", ""),
            "extra_features": [f for f in next_spec["features"] if f not in spec["features"]],
        }

    return json.dumps(result, ensure_ascii=False)


# ===========================================================================
# Tool 2: tier_set - Change user tier (for admin/payment integration)
# ===========================================================================

def _tier_set_handler(args: Dict[str, Any], **kwargs) -> str:
    tier = args.get("tier", "").lower().strip()
    reason = args.get("reason", "")

    if tier not in TIER_DEFINITIONS:
        valid = ", ".join(TIER_DEFINITIONS.keys())
        return json.dumps({
            "success": False,
            "error": f"Invalid tier '{tier}'. Valid options: {valid}"
        })

    old_tier = _get_current_tier()
    ok = _set_tier(tier)

    if ok:
        spec = TIER_DEFINITIONS[tier]
        return json.dumps({
            "success": True,
            "previous_tier": old_tier,
            "new_tier": tier,
            "new_tier_name": spec["name"],
            "reason": reason,
            "changed_at": datetime.now(timezone.utc).isoformat(),
        })
    return json.dumps({"success": False, "error": "Failed to update tier"})


# ===========================================================================
# Tool 3: tier_compare - Compare all tiers side by side
# ===========================================================================

def _tier_compare_handler(args: Dict[str, Any], **kwargs) -> str:
    include_features = args.get("include_features", True)

    comparison = {}
    for tid, tspec in TIER_DEFINITIONS.items():
        entry = {
            "name": tspec["name"],
            "price": tspec["price"],
            "period": tspec.get("price_period", "forever" if tspec["price"] == 0 else "month"),
            "daily_sessions": "无限" if tspec["daily_sessions"] == -1 else str(tspec["daily_sessions"]),
            "daily_calls": "无限" if tspec["daily_tool_calls"] == -1 else str(tspec["daily_tool_calls"]),
            "skills": "全部" if tspec["max_skills"] == -1 else str(tspec["max_skills"]),
            "memory": "无限" if tspec["max_memory_entries"] == -1 else str(tspec["max_memory_entries"]),
        }

        if include_features:
            all_feats = set()
            for ts in TIER_DEFINITIONS.values():
                all_feats.update(ts.get("features", []))
            entry["feature_matrix"] = {f: (f in tspec["features"]) for f in sorted(all_feats)}

        comparison[tid] = entry

    current = _get_current_tier()
    return json.dumps({
        "success": True,
        "current_tier": current,
        "tiers": comparison,
        "recommendation": _get_recommendation(current),
    }, ensure_ascii=False)


def _get_recommendation(current: str) -> str:
    recs = {
        "free": "如果你是内容创作者或重度用户，建议升级到创作者版(¥99/月)以解锁完整的视频制作工具链。普通轻度使用免费版已足够。",
        "creator": "创作者版已经覆盖了绝大多数场景。如果需要API接入或多Agent协作，可考虑专业版。",
        "pro": "你已是最高等级会员，享受所有功能！",
    }
    return recs.get(current, "")


# ===========================================================================
# Tool 4: tier_upgrade_prompt - Generate contextual upgrade message
# ===========================================================================

def _tier_upgrade_prompt_handler(args: Dict[str, Any], **kwargs) -> str:
    tool_name = args.get("blocked_tool", "")
    scenario = args.get("scenario", "general")
    tone = args.get("tone", "friendly")

    tier = _get_current_tier()
    spec = TIER_DEFINITIONS[tier]

    tiers_list = list(TIER_DEFINITIONS.keys())
    current_idx = tiers_list.index(tier) if tier in tiers_list else 0
    if current_idx >= len(tiers_list) - 1:
        return json.dumps({"success": True, "message": "你已经是最高等级会员！", "upgradable": False})

    next_tier = tiers_list[current_idx + 1]
    next_spec = TIER_DEFINITIONS[next_tier]

    reasons = spec.get("upgrade_reasons", [])
    extra_feats = [f for f in next_spec["features"] if f not in spec["features"]]
    feat_descs = [FEATURE_DESCRIPTIONS.get(f, f) for f in extra_feats[:5]]

    messages = {
        "tool_blocked": (
            f"🔒 '{tool_name}' 需要 {next_spec['name']} 才能使用。\n\n"
            f"升级到 {next_spec['name']} 后即可解锁：\n"
            + "\n".join(f"  ✅ {d}" for d in feat_descs)
            + f"\n\n💰 仅需 ¥{next_spec['price']}/{next_spec.get('price_period','月')}"
        ),
        "quota_limit": (
            f"⚠️ 你今天的免费使用次数已达上限。\n\n"
            f"升级到 {next_spec['name']} 可获得：\n"
            + (f"  📊 无限次调用\n" if next_spec["daily_tool_calls"] == -1 else f"  📊 每天{next_spec['daily_tool_calls']}次调用\n")
            + f"\n💰 ¥{next_spec['price']}/{next_spec.get('price_period','月')}"
        ),
        "general": (
            f"✨ 想要更多强大功能？\n\n"
            f"{next_spec['name']} (¥{next_spec['price']}/{next_spec.get('price_period','月')}) 包含：\n"
            + "\n".join(f"  ⭐ {d}" for d in feat_descs[:3])
            + f"\n\n还有 {len(extra_feats)-3} 项额外功能等你探索！"
        ),
    }

    template = messages.get(scenario, messages["general"])
    return json.dumps({
        "success": True,
        "message": template,
        "from_tier": tier,
        "to_tier": next_tier,
        "to_tier_name": next_spec["name"],
        "price": next_spec["price"],
        "extra_features": extra_feats,
        "upgradable": True,
    }, ensure_ascii=False)


# ===========================================================================
# Registration
# ===========================================================================

registry.register(name="tier_check", toolset="monetization",
    schema={"name": "tier_check", "description": "Check current subscription tier, feature availability, and remaining quotas.",
        "parameters": {"type": "object", "properties": {
            "tool_name": {"type": "string", "description": "Specific tool to check availability for"},
            "toolset": {"type": "string", "description": "Toolset to check"},
            "check_only": {"type": "boolean", "description": "Quick check only, skip quota details"},
        }}},
    handler=_tier_check_handler)

registry.register(name="tier_set", toolset="monetization",
    schema={"name": "tier_set", "description": "Change user subscription tier (admin/payment callback).",
        "parameters": {"type": "object", "properties": {
            "tier": {"type": "string", "enum": ["free", "creator", "pro"], "description": "Target tier"},
            "reason": {"type": "string", "description": "Reason for change (audit log)"},
        }, "required": ["tier"]}},
    handler=_tier_set_handler)

registry.register(name="tier_compare", toolset="monetization",
    schema={"name": "tier_compare", "description": "Compare all subscription tiers side-by-side with full feature matrix.",
        "parameters": {"type": "object", "properties": {
            "include_features": {"type": "boolean", "description": "Include detailed feature matrix (default: true)"},
        }}},
    handler=_tier_compare_handler)

registry.register(name="tier_upgrade_prompt", toolset="monetization",
    schema={"name": "tier_upgrade_prompt", "description": "Generate a contextual, persuasive upgrade message based on what the user tried to do.",
        "parameters": {"type": "object", "properties": {
            "blocked_tool": {"type": "string", "description": "Tool that was blocked (for targeted message)"},
            "scenario": {"type": "string", "enum": ["tool_blocked", "quota_limit", "general"], "description": "Upgrade trigger scenario"},
            "tone": {"type": "string", "enum": ["friendly", "urgent", "professional"], "description": "Message tone"},
        }}},
    handler=_tier_upgrade_prompt_handler)
