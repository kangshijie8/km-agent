"""BuiltinMemoryProvider — wraps three-layer memory as a MemoryProvider.

Always registered as the first provider. Cannot be disabled or removed.
This is the existing Kunming memory system exposed through the provider
interface for compatibility with the MemoryManager.

The actual storage logic lives in tools/memory_tool.py (MemoryStore).
This provider is a thin adapter that delegates to MemoryStore and
exposes the memory tool schema.

Three-layer architecture:
  - FACTS.md: environment knowledge, tool quirks, project conventions
  - EXPERIENCES.md: problem-solving records, operation outcomes
  - MODELS.md: learned rules, patterns, decision strategies
  - USER.md: user profile information
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from agent.memory_provider import MemoryProvider
from tools.registry import tool_error

logger = logging.getLogger(__name__)


class BuiltinMemoryProvider(MemoryProvider):
    """Built-in file-backed memory (FACTS.md + EXPERIENCES.md + MODELS.md + USER.md).

    Always active, never disabled by other providers. The `memory` tool
    is also registered in the tool registry with is_agent_tool=True and
    intercepted in run_agent.py for agent-level state injection (store kwarg).

    [R2-P1] get_tool_schemas() now returns [MEMORY_SCHEMA] to properly fulfill
    the MemoryProvider interface contract. When this provider is registered with
    MemoryManager, the manager can discover and route the memory tool correctly.
    Duplicate registration is prevented by run_agent.py's dedup guard on
    valid_tool_names.
    """

    def __init__(
        self,
        memory_store=None,
        memory_enabled: bool = False,
        user_profile_enabled: bool = False,
    ):
        self._store = memory_store
        self._memory_enabled = memory_enabled
        self._user_profile_enabled = user_profile_enabled
        self._loaded = False

    @property
    def name(self) -> str:
        return "builtin"

    def is_available(self) -> bool:
        """Built-in memory is always available."""
        return True

    def initialize(self, session_id: str, **kwargs) -> None:
        """Load memory from disk if not already loaded."""
        if self._loaded:
            return
        self._loaded = True
        if self._store is not None:
            self._store.load_from_disk()

    def system_prompt_block(self) -> str:
        """Return all memory layer content for the system prompt.

        Uses the frozen snapshot captured at load time. This ensures the
        system prompt stays stable throughout a session (preserving the
        prompt cache), even though the live entries may change via tool calls.
        """
        if not self._store:
            return ""

        parts = []
        if self._memory_enabled:
            for target in ("facts", "experiences", "models"):
                block = self._store.format_for_system_prompt(target)
                if block:
                    parts.append(block)
        if self._user_profile_enabled:
            user_block = self._store.format_for_system_prompt("user")
            if user_block:
                parts.append(user_block)

        return "\n\n".join(parts)

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """Recall relevant memories using the built-in hybrid search."""
        if not self._store or not query.strip():
            return ""
        result = self._store.recall(query)
        if not result.get("success") or not result.get("results"):
            return ""
        lines = ["[Recalled from memory:]"]
        for r in result["results"][:3]:
            lines.append(f"  [{r['target']}] {r['content'][:200]}")
        return "\n".join(lines)

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "") -> None:
        """Built-in memory doesn't auto-sync turns — writes happen via the memory tool."""

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Return the memory tool schema.

        [R2-P1] 返回MEMORY_SCHEMA以正确履行MemoryProvider接口契约。
        原实现返回空列表[]，理由是"memory工具在run_agent.py中被拦截处理"，
        但这导致MemoryManager无法发现和路由memory工具，违反接口语义：
        provider应声明其暴露的工具，使MemoryManager能正确路由调用。
        去重保护：run_agent.py在注入MemoryManager的tool schemas时，
        会跳过已在valid_tool_names中的工具名，避免重复注册。
        """
        # 延迟导入避免循环依赖：tools.memory_tool在导入时执行registry.register()
        from tools.memory_tool import MEMORY_SCHEMA
        return [MEMORY_SCHEMA]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        """Handle the memory tool call by delegating to memory_tool().

        [R2-P1] 实现handle_tool_call()，使BuiltinMemoryProvider能通过
        MemoryManager路由处理memory工具调用。使用self._store作为存储后端，
        与run_agent.py中agent-level拦截使用的是同一个MemoryStore实例。
        """
        if tool_name == "memory":
            # 延迟导入避免循环依赖
            from tools.memory_tool import memory_tool
            if self._store is None:
                return tool_error("Memory store is not available.", success=False)
            return memory_tool(
                action=args.get("action", ""),
                target=args.get("target", "facts"),
                content=args.get("content"),
                old_text=args.get("old_text"),
                query=args.get("query"),
                store=self._store,
            )
        return tool_error(f"Unknown tool: {tool_name}")

    def shutdown(self) -> None:
        """No cleanup needed — files are saved on every write."""

    # -- Property access for backward compatibility --------------------------

    @property
    def store(self):
        """Access the underlying MemoryStore for legacy code paths."""
        return self._store

    @property
    def memory_enabled(self) -> bool:
        return self._memory_enabled

    @property
    def user_profile_enabled(self) -> bool:
        return self._user_profile_enabled
