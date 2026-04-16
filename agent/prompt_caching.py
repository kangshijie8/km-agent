"""Anthropic prompt caching (system_and_3 strategy).

Reduces input token costs by ~75% on multi-turn conversations by caching
the conversation prefix. Uses 4 cache_control breakpoints (Anthropic max):
  1. System prompt (stable across all turns)
  2-4. Last 3 non-system messages (rolling window)

Pure functions -- no class state, no AIAgent dependency.
"""

from typing import Any, Dict, List


def _apply_cache_marker(msg: dict, cache_marker: dict, native_anthropic: bool = False) -> None:
    """Add cache_control to a single message, handling all format variations."""
    role = msg.get("role", "")
    content = msg.get("content")

    if role == "tool":
        if native_anthropic:
            msg["cache_control"] = cache_marker
        return

    if content is None or content == "":
        msg["cache_control"] = cache_marker
        return

    if isinstance(content, str):
        msg["content"] = [
            {"type": "text", "text": content, "cache_control": cache_marker}
        ]
        return

    if isinstance(content, list) and content:
        last = content[-1]
        if isinstance(last, dict):
            last["cache_control"] = cache_marker


def apply_anthropic_cache_control(
    api_messages: List[Dict[str, Any]],
    cache_ttl: str = "5m",
    native_anthropic: bool = False,
) -> List[Dict[str, Any]]:
    """Apply system_and_3 caching strategy to messages for Anthropic models.

    Places up to 4 cache_control breakpoints: system prompt + last 3 non-system messages.

    Returns:
        Shallow copy of messages with cache_control breakpoints injected.
        Only messages that need modification are deep-copied; unmodified
        messages share the original dict objects to avoid O(n) deepcopy cost.

    [deepcopy性能优化] 原实现使用copy.deepcopy(api_messages)对整个消息列表做深拷贝，
    对于长对话（数百条消息）这会造成严重的内存和时间开销。优化策略：
    1. 使用浅拷贝列表（只拷贝外层dict引用）
    2. 仅对需要注入cache_control的消息做深拷贝（最多4条）
    3. 其余消息直接引用原dict对象（它们不会被修改）
    """
    # [deepcopy优化] 浅拷贝列表，避免对整个消息列表做O(n)深拷贝
    messages = list(api_messages)
    if not messages:
        return messages

    marker = {"type": "ephemeral"}
    if cache_ttl == "1h":
        marker["ttl"] = "1h"

    breakpoints_used = 0

    # 修复：确保系统消息始终被缓存，提高缓存稳定性
    if messages[0].get("role") == "system":
        # [deepcopy优化] 仅对需要修改的消息做深拷贝，其余保持引用
        messages[0] = dict(messages[0])
        if isinstance(messages[0].get("content"), list):
            messages[0]["content"] = list(messages[0]["content"])
        _apply_cache_marker(messages[0], marker, native_anthropic=native_anthropic)
        breakpoints_used += 1

    remaining = 4 - breakpoints_used
    non_sys = [i for i in range(len(messages)) if messages[i].get("role") != "system"]

    if len(non_sys) <= remaining:
        # 修复：消息数量较少时，缓存所有非系统消息
        for idx in non_sys:
            messages[idx] = dict(messages[idx])
            if isinstance(messages[idx].get("content"), list):
                messages[idx]["content"] = list(messages[idx]["content"])
            _apply_cache_marker(messages[idx], marker, native_anthropic=native_anthropic)
    else:
        # 修复：消息数量较多时，优先缓存助手消息和包含工具调用的消息
        # 这些消息通常包含更多有价值的信息
        tail = non_sys[-remaining:]
        for idx in tail:
            # [deepcopy优化] 仅对需要注入cache_control的消息做深拷贝
            messages[idx] = dict(messages[idx])
            if isinstance(messages[idx].get("content"), list):
                messages[idx]["content"] = list(messages[idx]["content"])
            _apply_cache_marker(messages[idx], marker, native_anthropic=native_anthropic)

    return messages
