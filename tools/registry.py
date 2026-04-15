"""Central registry for all kunming-agent tools.

This module provides a centralized registry for all tools in the kunming-agent system.
Tools register themselves by importing this module and calling registry.register().
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ToolMetadata:
    """Metadata for a registered tool."""

    name: str
    toolset: str
    schema: dict
    handler: Callable[[dict, Any], str]
    check_fn: Optional[Callable[[], bool]] = None
    requires_env: List[str] = field(default_factory=list)
    requires_config: List[str] = field(default_factory=list)
    requires_env_var: Optional[str] = None
    dangerous: bool = False
    dangerous_patterns: Optional[List[tuple]] = None
    max_result_size_chars: Optional[int] = None
    is_agent_tool: bool = False  # True for tools requiring agent-level state (todo, memory, etc.)
    is_async: bool = False  # True if handler is a coroutine function
    emoji: Optional[str] = None  # Emoji icon for the tool


class ToolRegistry:
    """Central registry for all tools."""

    def __init__(self):
        self._tools: Dict[str, ToolMetadata] = {}
        self._toolsets: Dict[str, List[str]] = {}
        self._schemas: List[dict] = []
        self._pending_registrations: List[ToolMetadata] = []
        self._frozen = False
        self._lock = threading.RLock()

    def register(
        self,
        name: str,
        toolset: str,
        schema: dict,
        handler: Callable[[dict, Any], str],
        check_fn: Optional[Callable[[], bool]] = None,
        requires_env: Optional[List[str]] = None,
        requires_config: Optional[List[str]] = None,
        requires_env_var: Optional[str] = None,
        dangerous: bool = False,
        dangerous_patterns: Optional[List[tuple]] = None,
        allow_override: bool = False,
        emoji: Optional[str] = None,
        max_result_size_chars: Optional[int] = None,
        is_async: bool = False,  # For backward compatibility
        is_agent_tool: bool = False,  # True for tools requiring agent-level state
    ) -> None:
        """Register a tool with the registry.

        Args:
            name: The tool name (must be unique)
            toolset: The toolset this tool belongs to
            schema: The JSON schema for the tool's parameters
            handler: The function that implements the tool
            check_fn: Optional function to check if the tool is available
            requires_env: List of environment variables required by this tool
            requires_config: List of config keys required by this tool
            requires_env_var: Single env var name (for backward compat)
            dangerous: Whether this tool performs dangerous operations
            dangerous_patterns: Optional list of (pattern, description) tuples for dangerous command detection
            allow_override: Whether to allow overriding existing tool (default: False)
            emoji: Optional emoji for the tool (stored in schema metadata)
            max_result_size_chars: Optional maximum result size in characters
            is_agent_tool: Whether this tool requires agent-level state (todo, memory, etc.)

        Raises:
            ValueError: If tool name already exists and allow_override is False
        """
        # Check for duplicate registration
        # Note: In production, we warn about duplicates but allow them in test environments
        with self._lock:
            if name in self._tools and not allow_override:
                import os
                if os.getenv("KUNMING_TEST_MODE"):
                    pass
                else:
                    existing = self._tools[name]
                    raise ValueError(
                        f"Tool '{name}' is already registered in toolset '{existing.toolset}'. "
                        f"Use allow_override=True to force override."
                    )

            if self._frozen:
                self._pending_registrations.append(
                    ToolMetadata(
                        name=name,
                        toolset=toolset,
                        schema=schema,
                        handler=handler,
                        check_fn=check_fn,
                        requires_env=requires_env or [],
                        requires_config=requires_config or [],
                        requires_env_var=requires_env_var,
                        dangerous=dangerous,
                        dangerous_patterns=dangerous_patterns,
                        max_result_size_chars=max_result_size_chars,
                        is_agent_tool=is_agent_tool,
                        is_async=is_async,
                        emoji=emoji,
                    )
                )
                return

            all_requires_env = list(requires_env or [])
            if requires_env_var and requires_env_var not in all_requires_env:
                all_requires_env.append(requires_env_var)

            if emoji:
                schema = schema.copy()
                if "_metadata" not in schema:
                    schema["_metadata"] = {}
                schema["_metadata"]["emoji"] = emoji

            metadata = ToolMetadata(
                name=name,
                toolset=toolset,
                schema=schema,
                handler=handler,
                check_fn=check_fn,
                requires_env=all_requires_env,
                requires_config=list(requires_config or []),
                requires_env_var=requires_env_var,
                dangerous=dangerous,
                dangerous_patterns=dangerous_patterns,
                max_result_size_chars=max_result_size_chars,
                is_agent_tool=is_agent_tool,
                is_async=is_async,
                emoji=emoji,
            )

            if name in self._tools and allow_override:
                old_metadata = self._tools[name]
                if old_metadata.schema in self._schemas:
                    self._schemas.remove(old_metadata.schema)
                if old_metadata.toolset in self._toolsets and name in self._toolsets[old_metadata.toolset]:
                    self._toolsets[old_metadata.toolset].remove(name)

            self._tools[name] = metadata

            if toolset not in self._toolsets:
                self._toolsets[toolset] = []
            if name not in self._toolsets[toolset]:
                self._toolsets[toolset].append(name)

            self._schemas.append(schema)

    def deregister(self, name: str) -> bool:
        """Remove a tool from the registry.

        Returns True if the tool was found and removed, False otherwise.
        """
        with self._lock:
            metadata = self._tools.pop(name, None)
            if metadata is None:
                return False

            if metadata.schema in self._schemas:
                self._schemas.remove(metadata.schema)

            if metadata.toolset in self._toolsets and name in self._toolsets[metadata.toolset]:
                self._toolsets[metadata.toolset].remove(name)

            return True

    def get_tool(self, name: str) -> Optional[ToolMetadata]:
        """Get a tool's metadata by name."""
        return self._tools.get(name)

    def get_toolset_tools(self, toolset: str) -> List[str]:
        """Get all tool names in a toolset."""
        return self._toolsets.get(toolset, [])

    def list_tools(self) -> List[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def list_toolsets(self) -> List[str]:
        """List all registered toolset names."""
        return list(self._toolsets.keys())

    def get_schemas(self) -> List[dict]:
        """Get all tool schemas."""
        return self._schemas.copy()

    def get_all_tools(self) -> Dict[str, ToolMetadata]:
        """Get all registered tools."""
        return self._tools.copy()

    def get_emoji(self, name: str, default: str = "⚡") -> str:
        """Get the emoji for a tool.

        Args:
            name: The tool name
            default: Default emoji to return if not set

        Returns:
            The emoji string if set, default otherwise
        """
        tool = self._tools.get(name)
        if not tool:
            return default
        # Check ToolMetadata.emoji first, then schema metadata
        emoji = tool.emoji
        if emoji is None or emoji == "":
            emoji = tool.schema.get("_metadata", {}).get("emoji")
        if emoji is None or emoji == "":
            return default
        return emoji

    def get_tool_to_toolset_map(self) -> Dict[str, str]:
        """Get a mapping of tool names to their toolset names.

        Returns:
            Dictionary mapping tool names to toolset names
        """
        return {name: metadata.toolset for name, metadata in self._tools.items()}

    def get_toolset_requirements(self) -> Dict[str, dict]:
        """Get requirements for each toolset.

        Returns:
            Dictionary mapping toolset names to their requirements
        """
        requirements = {}
        for toolset_name, tool_names in self._toolsets.items():
            env_vars = set()
            config_keys = set()
            for tool_name in tool_names:
                tool = self._tools.get(tool_name)
                if tool:
                    env_vars.update(tool.requires_env)
                    config_keys.update(tool.requires_config)
            requirements[toolset_name] = {
                "env_vars": list(env_vars),
                "config_keys": list(config_keys),
            }
        return requirements

    def freeze(self):
        """Freeze the registry - no new registrations allowed.

        After freeze(), any register() calls will store tools in _pending_registrations
        for validation purposes but won't add them to the active registry.
        """
        with self._lock:
            self._frozen = True

    def unfreeze(self):
        """Unfreeze the registry - allow new registrations."""
        with self._lock:
            self._frozen = False
            self._pending_registrations.clear()

    def is_frozen(self) -> bool:
        """Check if the registry is frozen."""
        with self._lock:
            return self._frozen

    def get_pending_registrations(self) -> List[ToolMetadata]:
        """Get tools that were registered while frozen."""
        with self._lock:
            return self._pending_registrations.copy()

    def clear_pending_registrations(self):
        """Clear pending registrations list."""
        with self._lock:
            self._pending_registrations.clear()

    # -------------------------------------------------------------------------
    # Methods required by model_tools.py
    # -------------------------------------------------------------------------

    def dispatch(
        self,
        tool_name: str,
        params: dict,
        task_id: Optional[str] = None,
        enabled_tools: Optional[List[str]] = None,
        user_task: Optional[str] = None,
        **kwargs,
    ) -> str:
        """Dispatch a tool call to the appropriate handler.

        This is the main entry point for tool execution from model_tools.py.

        Args:
            tool_name: The name of the tool to call
            params: The parameters to pass to the tool
            task_id: Optional task ID for tracking
            enabled_tools: Optional list of enabled tool names (for sandboxing)
            user_task: Optional user task description

        Returns:
            The tool's result as a JSON string
        """
        # Check if tool is enabled (sandbox check)
        if enabled_tools is not None and tool_name not in enabled_tools:
            return json.dumps(
                {"error": f"Tool '{tool_name}' is not enabled in this sandbox"},
                ensure_ascii=False,
            )

        # Get tool from this registry instance
        tool = self.get_tool(tool_name)
        if not tool:
            return json.dumps(
                {"error": f"Unknown tool: '{tool_name}'"}, ensure_ascii=False
            )

        # Check if tool is available
        if not self.check_tool_availability_single(tool_name):
            missing = []
            for env_var in tool.requires_env:
                if not os.getenv(env_var):
                    missing.append(f"{env_var} environment variable")
            if missing:
                return json.dumps(
                    {
                        "error": f"Tool '{tool_name}' is not available. Missing: {', '.join(missing)}"
                    },
                    ensure_ascii=False,
                )

        # Call the handler directly
        try:
            if tool.is_async:
                from tools.async_bridge import run_async
                result = run_async(tool.handler(params, task_id=task_id, **kwargs))
            else:
                result = tool.handler(params, task_id=task_id, **kwargs)

            if isinstance(result, dict):
                return json.dumps(result, ensure_ascii=False)
            return result
        except Exception as e:
            logger.error("Tool '%s' failed: %s", tool_name, e)
            logger.debug(traceback.format_exc())
            return json.dumps(
                {"error": f"Tool '{tool_name}' failed: {type(e).__name__}: {str(e)}"},
                ensure_ascii=False,
            )

    def get_all_tool_names(self) -> List[str]:
        """Return all registered tool names (sorted for deterministic ordering)."""
        return sorted(self.list_tools())

    def is_toolset_available(self, toolset_name: str) -> bool:
        """Check if a toolset is available (all its tools are available).

        Args:
            toolset_name: The name of the toolset to check

        Returns:
            True if all tools in the toolset are available, False otherwise
        """
        tool_names = self._toolsets.get(toolset_name, [])
        if not tool_names:
            return True  # Empty toolset is considered available

        for name in tool_names:
            if not self.check_tool_availability_single(name):
                return False
        return True

    def check_toolset_requirements(self) -> Dict[str, bool]:
        """Check availability status for all toolsets.

        Returns:
            Dictionary mapping toolset names to their availability (True/False)
        """
        result = {}
        for toolset_name in self._toolsets:
            result[toolset_name] = self.is_toolset_available(toolset_name)
        return result

    def get_agent_tool_names(self) -> List[str]:
        """Return names of all tools marked with is_agent_tool=True."""
        return [name for name, tool in self._tools.items() if tool.is_agent_tool]

    def get_toolset_for_tool(self, tool_name: str) -> Optional[str]:
        """Return the toolset a tool belongs to."""
        tool = self._tools.get(tool_name)
        if tool:
            return tool.toolset
        return None

    def get_available_toolsets(self) -> Dict[str, dict]:
        """Return toolset availability info for UI display."""
        result = {}
        for toolset_name in self._toolsets:
            tool_names = self._toolsets[toolset_name]
            available_count = sum(
                1 for name in tool_names if self.check_tool_availability_single(name)
            )
            result[toolset_name] = {
                "total": len(tool_names),
                "available": available_count,
                "tools": tool_names,
            }
        return result

    def check_tool_availability(self, quiet: bool = False) -> Tuple[List[str], List[dict]]:
        """Return (available_toolsets, unavailable_info).

        Args:
            quiet: If True, suppress logging

        Returns:
            Tuple of (list of available toolset names, list of unavailable toolset info)
        """
        available = []
        unavailable = []

        for toolset_name in self._toolsets:
            tool_names = self._toolsets[toolset_name]
            is_available = all(
                self.check_tool_availability_single(name) for name in tool_names
            )
            if is_available:
                available.append(toolset_name)
            else:
                # Collect unavailable toolsets with their names
                unavailable.append({"name": toolset_name})

        return available, unavailable

    def check_tool_availability_single(self, name: str) -> bool:
        """Check if a single tool is available (has required env vars/config)."""
        tool = self._tools.get(name)
        if not tool:
            return False

        # Run custom check function if provided
        if tool.check_fn:
            try:
                if not tool.check_fn():
                    return False
            except Exception:
                logger.debug("check_fn for tool '%s' raised exception", name, exc_info=True)
                return False

        # Check required environment variables
        for env_var in tool.requires_env:
            if not os.getenv(env_var):
                return False

        # Check required config keys
        if tool.requires_config:
            try:
                from kunming_cli.config import load_cli_config

                cfg = load_cli_config()
                for key_path in tool.requires_config:
                    parts = key_path.split(".")
                    value = cfg
                    for part in parts:
                        if isinstance(value, dict):
                            value = value.get(part)
                        else:
                            value = None
                            break
                    if value is None:
                        return False
            except Exception:
                return False

        return True

    def get_definitions(self, tool_names: Optional[List[str]] = None, quiet: bool = False) -> List[dict]:
        """Get tool definitions (schemas) for the specified tools.

        Args:
            tool_names: Optional list of tool names to filter by. If None, returns all.
            quiet: If True, suppress logging

        Returns:
            List of OpenAI-format tool definitions: [{"type": "function", "function": schema}, ...]
        """
        # Cache check_fn results to avoid calling the same check_fn multiple times
        check_fn_cache: Dict[Callable, bool] = {}

        def check_with_cache(tool: ToolMetadata) -> bool:
            """Check tool availability with caching for shared check_fn."""
            # Check required environment variables first
            for env_var in tool.requires_env:
                if not os.getenv(env_var):
                    return False

            # Check required config keys
            if tool.requires_config:
                try:
                    from kunming_cli.config import load_cli_config

                    cfg = load_cli_config()
                    for key_path in tool.requires_config:
                        parts = key_path.split(".")
                        value = cfg
                        for part in parts:
                            if isinstance(value, dict):
                                value = value.get(part)
                            else:
                                value = None
                                break
                        if value is None:
                            return False
                except Exception:
                    return False

            # Check custom check_fn with caching
            if tool.check_fn:
                if tool.check_fn not in check_fn_cache:
                    try:
                        check_fn_cache[tool.check_fn] = tool.check_fn()
                    except Exception:
                        logger.debug("check_fn for tool '%s' raised exception", tool.name, exc_info=True)
                        check_fn_cache[tool.check_fn] = False
                return check_fn_cache[tool.check_fn]

            return True

        if tool_names is None:
            # Return all available tools in OpenAI format
            return [
                {"type": "function", "function": schema}
                for schema in self._schemas
                if check_with_cache(self._tools.get(schema.get("name", "")))
            ]

        schemas = []
        for name in tool_names:
            tool = self._tools.get(name)
            if tool and check_with_cache(tool):
                schemas.append({"type": "function", "function": tool.schema})
            elif not tool and not quiet:
                logger.warning(f"Tool '{name}' not found in registry")
        return schemas

    def get_schema(self, tool_name: str) -> Optional[dict]:
        """Get the schema for a specific tool.

        Args:
            tool_name: The name of the tool

        Returns:
            The tool's schema dict, or None if not found
        """
        tool = self._tools.get(tool_name)
        if tool:
            return tool.schema
        return None

    def get_max_result_size(self, tool_name: str, default: int = 100_000) -> int | float:
        """Get the maximum result size for a specific tool.

        Args:
            tool_name: The name of the tool
            default: Default value if tool not found or no limit set

        Returns:
            Maximum result size in characters, or float('inf') for unlimited
        """
        tool = self._tools.get(tool_name)
        if tool and tool.max_result_size_chars is not None:
            return tool.max_result_size_chars
        return default


# Global registry instance
registry = ToolRegistry()


# Convenience function for backward compatibility
def register_tool(
    name: str,
    toolset: str,
    schema: dict,
    handler: Callable[[dict, Any], str],
    check_fn: Optional[Callable[[], bool]] = None,
    requires_env: Optional[List[str]] = None,
    requires_config: Optional[List[str]] = None,
    requires_env_var: Optional[str] = None,
    dangerous: bool = False,
    dangerous_patterns: Optional[List[tuple]] = None,
    allow_override: bool = False,
    emoji: Optional[str] = None,
    max_result_size_chars: Optional[int] = None,
    is_agent_tool: bool = False,
) -> None:
    """Register a tool with the global registry."""
    registry.register(
        name=name,
        toolset=toolset,
        schema=schema,
        handler=handler,
        check_fn=check_fn,
        requires_env=requires_env,
        requires_config=requires_config,
        requires_env_var=requires_env_var,
        dangerous=dangerous,
        dangerous_patterns=dangerous_patterns,
        allow_override=allow_override,
        emoji=emoji,
        max_result_size_chars=max_result_size_chars,
        is_agent_tool=is_agent_tool,
    )


def _detect_dangerous_patterns(
    command: str,
    patterns: List[tuple],
) -> List[tuple]:
    """Detect dangerous patterns in a command string.

    Args:
        command: The command string to check
        patterns: List of (pattern, description) tuples where pattern is a regex string

    Returns:
        List of (matched_text, description) tuples for matched patterns
    """
    matches = []
    for pattern_str, description in patterns:
        try:
            for match in re.finditer(pattern_str, command, re.IGNORECASE):
                matched_text = match.group(0)
                # Truncate long matches for display
                if len(matched_text) > 80:
                    matched_text = matched_text[:77] + "..."
                matches.append((matched_text, description))
        except re.error:
            # Skip invalid regex patterns
            continue
    return matches


def _format_approval_prompt(
    tool_name: str,
    params: dict,
    dangerous_matches: Optional[List[tuple]] = None,
    dangerous_patterns: Optional[List[tuple]] = None,
) -> str:
    """Format a user-friendly approval prompt for dangerous commands.

    Args:
        tool_name: The name of the tool being called
        params: The parameters being passed to the tool
        dangerous_matches: List of (matched_text, description) tuples from pattern detection
        dangerous_patterns: The original dangerous patterns for reference

    Returns:
        Formatted prompt string for user approval
    """
    lines = []
    lines.append(f"The tool '{tool_name}' is about to execute a potentially dangerous operation.")
    lines.append("")

    # Show what will be executed
    lines.append("Operation details:")
    for key, value in params.items():
        # Truncate long values
        display_value = str(value)
        if len(display_value) > 200:
            display_value = display_value[:197] + "..."
        lines.append(f"  {key}: {display_value}")

    # Show detected dangerous patterns
    if dangerous_matches:
        lines.append("")
        lines.append("Detected potentially dangerous patterns:")
        for matched_text, description in dangerous_matches:
            lines.append(f"  - {description}")
            lines.append(f"    Matched: {matched_text}")

    lines.append("")
    lines.append("Do you want to allow this operation? (yes/no)")

    return "\n".join(lines)


def _ask_for_approval(prompt: str, timeout: Optional[int] = None) -> bool:
    """Ask the user for approval via interactive prompt.

    Args:
        prompt: The prompt to display to the user
        timeout: Optional timeout in seconds

    Returns:
        True if approved, False otherwise
    """
    # Check if we're in a non-interactive environment
    if not sys.stdin.isatty():
        logger.warning("Cannot request approval in non-interactive mode")
        return False

    print(prompt)

    try:
        if timeout:
            # Use select for timeout on Unix, threading on Windows
            if os.name == "posix":
                import select

                print(f"(timeout in {timeout}s) ", end="", flush=True)
                ready, _, _ = select.select([sys.stdin], [], [], timeout)
                if ready:
                    response = sys.stdin.readline().strip().lower()
                else:
                    print("\nTimeout - operation not approved")
                    return False
            else:
                # Windows: use threading.Timer-based timeout since select doesn't work on stdin
                result = [None]
                def _read_input():
                    try:
                        result[0] = input().strip().lower()
                    except EOFError:
                        result[0] = ""
                t = threading.Thread(target=_read_input, daemon=True)
                t.start()
                t.join(timeout=timeout)
                if t.is_alive():
                    print("\nTimeout - operation not approved")
                    return False
                response = result[0] or ""
        else:
            response = input().strip().lower()

        return response in ("yes", "y", "true", "1")
    except (EOFError, KeyboardInterrupt):
        print("\nOperation not approved")
        return False


def dispatch_tool(
    tool_name: str,
    params: dict,
    task_id: Optional[str] = None,
    require_approval: bool = True,
    approval_mode: Optional[str] = None,
    **kwargs,
) -> str:
    """Dispatch a tool call to the appropriate handler.

    Args:
        tool_name: The name of the tool to call
        params: The parameters to pass to the tool
        task_id: Optional task ID for tracking
        require_approval: Whether to require user approval for dangerous tools
        approval_mode: Optional approval mode override ('auto', 'ask', 'off')

    Returns:
        The tool's result as a JSON string
    """
    tool = registry.get_tool(tool_name)
    if not tool:
        return json.dumps(
            {"error": f"Tool '{tool_name}' not found"}, ensure_ascii=False
        )

    # Check if tool is available
    if not registry.check_tool_availability_single(tool_name):
        missing = []
        for env_var in tool.requires_env:
            if not os.getenv(env_var):
                missing.append(f"{env_var} environment variable")
        if missing:
            return json.dumps(
                {
                    "error": f"Tool '{tool_name}' is not available. Missing: {', '.join(missing)}"
                },
                ensure_ascii=False,
            )

    # Check for dangerous operations
    if tool.dangerous and require_approval:
        # Get approval mode from config if not provided
        if approval_mode is None:
            try:
                from kunming_cli.config import load_cli_config

                cfg = load_cli_config()
                approval_mode = cfg.get("security", {}).get("dangerous_tool_approval", "ask")
            except Exception:
                approval_mode = "ask"

        # Check for YOLO mode (auto-approve)
        if os.getenv("KUNMING_YOLO_MODE"):
            approval_mode = "auto"

        if approval_mode == "off":
            return json.dumps(
                {"error": f"Tool '{tool_name}' is disabled (dangerous_tool_approval=off)"},
                ensure_ascii=False,
            )

        # Detect dangerous patterns
        dangerous_matches = None
        if tool.dangerous_patterns:
            # Extract command from params (common parameter names)
            command = params.get("command") or params.get("cmd") or params.get("script", "")
            if command:
                dangerous_matches = _detect_dangerous_patterns(
                    command, tool.dangerous_patterns
                )

        # Always ask for approval if dangerous, unless in auto mode
        if approval_mode != "auto":
            prompt = _format_approval_prompt(
                tool_name, params, dangerous_matches, tool.dangerous_patterns
            )
            if not _ask_for_approval(prompt):
                return json.dumps(
                    {"error": f"Tool '{tool_name}' execution was not approved by user"},
                    ensure_ascii=False,
                )

    # Call the handler
    try:
        start_time = time.time()
        if tool.is_async:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                # Already inside an event loop — create a new thread to run the coroutine
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    result = pool.submit(
                        asyncio.run, tool.handler(params, task_id=task_id, **kwargs)
                    ).result()
            else:
                result = asyncio.run(tool.handler(params, task_id=task_id, **kwargs))
        else:
            result = tool.handler(params, task_id=task_id, **kwargs)
        elapsed = time.time() - start_time

        # Log slow tool calls
        if elapsed > 30:
            logger.warning(f"Tool '{tool_name}' took {elapsed:.1f}s to complete")

        if isinstance(result, dict):
            if result.get("error") and result.get("success") is False:
                error_result = {"error": result["error"]}
                for k, v in result.items():
                    if k not in ("error", "success"):
                        error_result[k] = v
                result = error_result
            elif result.get("success") is False and result.get("message"):
                error_result = {"error": result["message"]}
                for k, v in result.items():
                    if k not in ("success", "message"):
                        error_result[k] = v
                result = error_result
            return json.dumps(result, ensure_ascii=False)
        return result
    except Exception as e:
        logger.error("Tool '%s' failed: %s", tool_name, e)
        logger.debug(traceback.format_exc())
        return json.dumps(
            {"error": f"Tool '{tool_name}' failed: {str(e)}"}, ensure_ascii=False
        )


# Import common utilities for tool implementations
def truncate_output(output: str, max_chars: int = 10000) -> str:
    """Truncate output to max_chars, adding ellipsis if truncated."""
    if len(output) > max_chars:
        return output[:max_chars] + f"\n\n... [output truncated, {len(output) - max_chars} more characters]"
    return output


def sanitize_path(path: str, allow_relative: bool = True) -> str:
    """Sanitize a file path to prevent directory traversal attacks.

    Args:
        path: The path to sanitize
        allow_relative: Whether to allow relative paths (..)

    Returns:
        Sanitized path or raises ValueError if unsafe
    """
    # Normalize the path
    normalized = os.path.normpath(path)

    # Check for directory traversal
    if not allow_relative and ".." in normalized:
        raise ValueError(f"Path contains directory traversal: {path}")

    # Check for null bytes
    if "\x00" in normalized:
        raise ValueError(f"Path contains null bytes: {path}")

    return normalized


def format_json_result(data: Any, indent: int = 2) -> str:
    """Format data as a JSON string with proper error handling."""
    try:
        return json.dumps(data, indent=indent, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": f"Failed to serialize result: {e}"})


def safe_execute(
    func: Callable[..., Any],
    *args,
    default_error: str = "Operation failed",
    **kwargs
) -> str:
    """Safely execute a function and return a JSON result.

    Args:
        func: The function to execute
        *args: Positional arguments for the function
        default_error: Default error message if execution fails
        **kwargs: Keyword arguments for the function

    Returns:
        JSON string with result or error
    """
    try:
        result = func(*args, **kwargs)
        return format_json_result({"success": True, "result": result})
    except Exception as e:
        logger.error("safe_execute failed: %s", e)
        return format_json_result({"success": False, "error": str(e) or default_error})


# Shell command escaping utilities
def escape_shell_arg(arg: str) -> str:
    """Escape a string for safe use as a shell argument."""
    if sys.platform == "win32":
        import subprocess
        return subprocess.list2cmdline([arg])
    return shlex.quote(arg)


def escape_shell_command(command: str) -> str:
    """Escape special characters in a shell command string."""
    if sys.platform == "win32":
        import subprocess
        return subprocess.list2cmdline([command])
    return shlex.quote(command)


def tool_error(message: str, tool_name: str = "", success: bool = None) -> str:
    """Format an error message for tool execution failures.

    Args:
        message: The error message
        tool_name: Optional name of the tool that failed
        success: Optional success flag (typically False for errors)

    Returns:
        JSON formatted error string
    """
    error_data = {"error": message}
    if tool_name:
        error_data["tool"] = tool_name
    if success is not None:
        error_data["success"] = success
    return json.dumps(error_data, ensure_ascii=False)
