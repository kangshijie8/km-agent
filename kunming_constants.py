"""Shared constants for Kunming Agent.

Import-safe module with no dependencies — can be imported from anywhere
without risk of circular imports.
"""

import os
import re
from datetime import datetime, timezone
from pathlib import Path


def get_kunming_home() -> Path:
    """Return the Kunming home directory (default: ~/.kunming).

    Reads KUNMING_HOME env var, falls back to ~/.kunming.
    This is the single source of truth — all other copies should import this.
    """
    return Path(os.getenv("KUNMING_HOME", Path.home() / ".kunming"))


def _get_default_kunming_home() -> Path:
    """Return the default (pre-profile) KUNMING_HOME path.

    Always ``~/.kunming`` — anchored to the user's home,
    NOT to the current KUNMING_HOME (which may itself be a profile).
    """
    return Path.home() / ".kunming"


def get_optional_skills_dir(default: Path | None = None) -> Path:
    """Return the optional-skills directory, honoring package-manager wrappers.

    Packaged installs may ship ``optional-skills`` outside the Python package
    tree and expose it via ``KUNMING_OPTIONAL_SKILLS``.
    """
    override = os.getenv("KUNMING_OPTIONAL_SKILLS", "").strip()
    if override:
        return Path(override)
    if default is not None:
        return default
    return get_kunming_home() / "optional-skills"


def get_kunming_dir(new_subpath: str, old_name: str) -> Path:
    """Resolve a Kunming subdirectory with backward compatibility.

    New installs get the consolidated layout (e.g. ``cache/images``).
    Existing installs that already have the old path (e.g. ``image_cache``)
    keep using it — no migration required.

    Args:
        new_subpath: Preferred path relative to KUNMING_HOME (e.g. ``"cache/images"``).
        old_name: Legacy path relative to KUNMING_HOME (e.g. ``"image_cache"``).

    Returns:
        Absolute ``Path`` — old location if it exists on disk, otherwise the new one.
    """
    home = get_kunming_home()
    old_path = home / old_name
    if old_path.exists():
        return old_path
    return home / new_subpath


def display_kunming_home() -> str:
    """Return a user-friendly display string for the current KUNMING_HOME.

    Uses ``~/`` shorthand for readability::

        default:  ``~/.kunming``
        profile:  ``~/.kunming/profiles/coder``
        custom:   ``/opt/kunming-custom``

    Use this in **user-facing** print/log messages instead of hardcoding
    ``~/.kunming``.  For code that needs a real ``Path``, use
    :func:`get_kunming_home` instead.
    """
    home = get_kunming_home()
    try:
        return "~/" + str(home.relative_to(Path.home()))
    except ValueError:
        return str(home)


VALID_REASONING_EFFORTS = ("xhigh", "high", "medium", "low", "minimal")


def parse_reasoning_effort(effort: str) -> dict | None:
    """Parse a reasoning effort level into a config dict.

    Valid levels: "xhigh", "high", "medium", "low", "minimal", "none".
    Returns None when the input is empty or unrecognized (caller uses default).
    Returns {"enabled": False} for "none".
    Returns {"enabled": True, "effort": <level>} for valid effort levels.
    """
    if not effort or not effort.strip():
        return None
    effort = effort.strip().lower()
    if effort == "none":
        return {"enabled": False}
    if effort in VALID_REASONING_EFFORTS:
        return {"enabled": True, "effort": effort}
    return None


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODELS_URL = f"{OPENROUTER_BASE_URL}/models"
OPENROUTER_CHAT_URL = f"{OPENROUTER_BASE_URL}/chat/completions"

AI_GATEWAY_BASE_URL = "https://ai-gateway.vercel.sh/v1"
AI_GATEWAY_MODELS_URL = f"{AI_GATEWAY_BASE_URL}/models"
AI_GATEWAY_CHAT_URL = f"{AI_GATEWAY_BASE_URL}/chat/completions"

NOUS_API_BASE_URL = "https://inference-api.kunming.dev/v1"
NOUS_API_CHAT_URL = f"{NOUS_API_BASE_URL}/chat/completions"

# 记忆保护关键词 — 集中定义，避免 memory_tool.py 和 memory_distillation.py 两处不同步
# 含 "critical"（合并自 memory_tool.py 的版本），用于 Ebbinghaus 衰减和蒸馏驱逐时的保护判定
# 修改此列表时只需改这一处，所有消费方自动同步
_MEMORY_PROTECTED_KEYWORDS = (
    "preference", "always", "never", "must", "required", "important", "critical",
    "必须", "永远", "不要", "重要", "关键", "务必", "绝不", "一定", "禁止", "只能", "从不", "偏好",
)

# 整合: 统一 CJK 感知的 token 估算函数，消除 context_compressor.py / model_metadata.py / skills_tool.py 三处重复实现 [H8/H9/H10]
# 基于 context_compressor.py 的版本（最精确：拉丁4字符/token，CJK 0.5字符/token，含韩文范围）
_CHARS_PER_TOKEN_LATIN = 4
_CHARS_PER_TOKEN_CJK = 0.5
_CJK_CHAR_RE = re.compile(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]')


def estimate_tokens_cjk_aware(text: str) -> int:
    """Estimate token count with CJK awareness.

    Latin text: ~4 chars per token.
    CJK text (Chinese, Japanese Hiragana/Katakana, Korean): ~0.5 chars per token (2 tokens per char).
    This is the single source of truth — all other copies should import this.
    """
    if not text:
        return 0
    cjk_count = len(_CJK_CHAR_RE.findall(text))
    latin_count = len(text) - cjk_count
    return int(latin_count / _CHARS_PER_TOKEN_LATIN + cjk_count / _CHARS_PER_TOKEN_CJK)


# 整合: 统一 UTC ISO 时间戳函数，消除 memory_distillation/experience_tool/analytics_tool/status.py/metrics.py 五处重复定义 [T1]
def utc_now_iso() -> str:
    """Return current UTC time in ISO 8601 format. Single source of truth for all _now_iso/_utc_now_iso calls."""
    return datetime.now(timezone.utc).isoformat()


# 整合: 统一混合搜索权重常量，消除 memory_tool/error_learning 两处独立硬编码 [S1]
# FTS关键词匹配权重与SimHash向量相似度权重之和为1.0
HYBRID_SEARCH_FTS_WEIGHT = 0.6
HYBRID_SEARCH_VECTOR_WEIGHT = 0.4


# 整合: 统一 PROVIDER_ALIASES 字典，合并 auth.py 和 models.py 两处重复定义 [M3]
# auth.py 独有: qwen-cli, qwen-oauth, local server aliases (lmstudio/ollama/vllm/llamacpp等)
# models.py 独有: deep-seek, dashscope, aliyun, qwen, alibaba-cloud
PROVIDER_ALIASES = {
    "glm": "zai", "z-ai": "zai", "z.ai": "zai", "zhipu": "zai",
    "google": "gemini", "google-gemini": "gemini", "google-ai-studio": "gemini",
    "kimi": "kimi-coding", "moonshot": "kimi-coding",
    "minimax-china": "minimax-cn", "minimax_cn": "minimax-cn",
    "claude": "anthropic", "claude-code": "anthropic",
    "github": "copilot", "github-copilot": "copilot",
    "github-models": "copilot", "github-model": "copilot",
    "github-copilot-acp": "copilot-acp", "copilot-acp-agent": "copilot-acp",
    "aigateway": "ai-gateway", "vercel": "ai-gateway", "vercel-ai-gateway": "ai-gateway",
    "opencode": "opencode-zen", "zen": "opencode-zen",
    "qwen-portal": "qwen-oauth", "qwen-cli": "qwen-oauth", "qwen-oauth": "qwen-oauth",
    "hf": "huggingface", "hugging-face": "huggingface", "huggingface-hub": "huggingface",
    "go": "opencode-go", "opencode-go-sub": "opencode-go",
    "kilo": "kilocode", "kilo-code": "kilocode", "kilo-gateway": "kilocode",
    # models.py 独有条目
    "deep-seek": "deepseek",
    "dashscope": "alibaba", "aliyun": "alibaba", "qwen": "alibaba", "alibaba-cloud": "alibaba",
    # Local server aliases - route through the generic custom provider
    "lmstudio": "custom", "lm-studio": "custom", "lm_studio": "custom",
    "ollama": "custom", "vllm": "custom", "llamacpp": "custom",
    "llama.cpp": "custom", "llama-cpp": "custom",
}

# 整合: 统一 PLATFORMS 字典，合并 tools_config.py 和 skills_config.py 两处重复定义 [H4]
# 以 tools_config.py 的 dict 结构为权威版本（含 label 和 default_toolset）
PLATFORMS = {
    "cli":      {"label": "🖥️ CLI",       "default_toolset": "kunming-cli"},
    "telegram": {"label": "[MOBILE] Telegram",   "default_toolset": "kunming-telegram"},
    "discord":  {"label": "[CHAT] Discord",    "default_toolset": "kunming-discord"},
    "slack":    {"label": "[WORK] Slack",      "default_toolset": "kunming-slack"},
    "whatsapp": {"label": "[MOBILE] WhatsApp",   "default_toolset": "kunming-whatsapp"},
    "signal":   {"label": "[HOME] Signal",     "default_toolset": "kunming-signal"},
    "bluebubbles": {"label": "💙 BlueBubbles", "default_toolset": "kunming-bluebubbles"},
    "homeassistant": {"label": "🏠 Home Assistant", "default_toolset": "kunming-homeassistant"},
    "email":    {"label": "📧 Email",      "default_toolset": "kunming-email"},
    "matrix":   {"label": "[CHAT] Matrix",     "default_toolset": "kunming-matrix"},
    "dingtalk": {"label": "[CHAT] DingTalk", "default_toolset": "kunming-dingtalk"},
    "feishu":   {"label": "🪶 Feishu", "default_toolset": "kunming-feishu"},
    "wecom":    {"label": "[CHAT] WeCom", "default_toolset": "kunming-wecom"},
    "api_server": {"label": "🌐 API Server", "default_toolset": "kunming-api-server"},
    "mattermost": {"label": "[CHAT] Mattermost", "default_toolset": "kunming-mattermost"},
    "webhook":  {"label": "🔗 Webhook", "default_toolset": "kunming-webhook"},
}
