"""
ToolContext -- Unrestricted Tool Access for Reward Functions

A per-rollout handle that gives reward/verification functions direct access to
ALL kunming-agent tools, scoped to the rollout's task_id. The same task_id means
the terminal/browser session is the SAME one the model used during its rollout --
all state (files, processes, browser tabs) is preserved.

The verifier author decides which tools to use. Nothing is hardcoded or gated.

Example usage in a compute_reward():
    async def compute_reward(self, item, result, ctx):
        # Run tests in the model's terminal sandbox
        test = ctx.terminal("pytest -v")
        if test["exit_code"] == 0:
            return 1.0

        # Check if a file was created
        content = ctx.read_file("/workspace/solution.py")
        if content.get("content"):
            return 0.5

        return 0.0
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

import asyncio
import concurrent.futures

from model_tools import handle_function_call
from tools.terminal_tool import cleanup_vm
from tools.browser_tool import cleanup_browser

logger = logging.getLogger(__name__)

# Thread pool for running sync tool calls that internally use asyncio.run()
_tool_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)


def _run_tool_in_thread(tool_name: str, arguments: Dict[str, Any], task_id: str) -> str:
    """
    Run a tool call in a thread pool executor so backends that use asyncio.run()
    internally (modal, docker, daytona) get a clean event loop.

    If we're already in an async context, executes handle_function_call() in a
    disposable worker thread and blocks for the result.
    If not (e.g., called from sync code), runs directly.
    """
    try:
        loop = asyncio.get_running_loop()
        # We're in an async context -- need to run in thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                handle_function_call, tool_name, arguments, task_id
            )
            return future.result(timeout=300)
    except RuntimeError:
        # No running event loop -- safe to call directly
        return handle_function_call(tool_name, arguments, task_id)


class ToolContext:
    """
    Open-ended access to all kunming-agent tools for a specific rollout.

    Passed to compute_reward() so verifiers can use any tool they need:
    terminal commands, file reads/writes, web searches, browser automation, etc.
    All calls share the rollout's task_id for session isolation.
    """

    def __init__(self, task_id: str):
        self.task_id = task_id

    # -------------------------------------------------------------------------
    # Terminal tools
    # -------------------------------------------------------------------------

    def terminal(self, command: str, timeout: int = 180) -> Dict[str, Any]:
        """
        Run a command in the rollout's terminal session.

        Args:
            command: Shell command to execute
            timeout: Command timeout in seconds

        Returns:
            Dict with 'exit_code' (int) and 'output' (str)
        """
        import os
        backend = os.getenv("TERMINAL_ENV", "local")
        logger.debug("ToolContext.terminal [%s backend] task=%s: %s", backend, self.task_id[:8], command[:100])

        # Run via thread helper so modal/docker/daytona backends' asyncio.run() doesn't deadlock
        result = _run_tool_in_thread(
            "terminal",
            {"command": command, "timeout": timeout},
            self.task_id,
        )
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"exit_code": -1, "output": result}

    # -------------------------------------------------------------------------
    # File tools
    # -------------------------------------------------------------------------

    def read_file(self, path: str) -> Dict[str, Any]:
        """
        Read a file from the rollout's filesystem.

        Args:
            path: File path to read

        Returns:
            Dict with file content or error
        """
        result = handle_function_call(
            "read_file", {"path": path}, task_id=self.task_id
        )
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"error": result}

    def write_file(self, path: str, content: str) -> Dict[str, Any]:
        """
        Write a TEXT file in the rollout's filesystem.

        Uses a shell heredoc under the hood, so this is only safe for text content.
        For binary files (images, compiled artifacts, etc.), use upload_file() instead.

        Args:
            path: File path to write
            content: Text content to write

        Returns:
            Dict with success status or error
        """
        result = handle_function_call(
            "write_file", {"path": path, "content": content}, task_id=self.task_id
        )
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"error": result}

    def upload_file(self, local_path: str, remote_path: str) -> Dict[str, Any]:
        """
        Upload a local file to the rollout's sandbox (binary-safe).

        Unlike write_file() which passes content through a shell heredoc (text-only),
        this method base64-encodes the file and decodes it inside the sandbox.
        Safe for any file type: binaries, images, archives, etc.

        For large files (>1MB), the content is split into chunks to avoid
        hitting shell command-length limits.

        Args:
            local_path: Path to a local file on the host
            remote_path: Destination path inside the sandbox

        Returns:
            Dict with 'exit_code' and 'output'
        """
        import base64
        from pathlib import Path as _Path

        local = _Path(local_path)
        if not local.exists():
            return {"exit_code": -1, "output": f"Local file not found: {local_path}"}

        raw = local.read_bytes()
        b64 = base64.b64encode(raw).decode("ascii")

        # Ensure parent directory exists in the sandbox
        parent = str(_Path(remote_path).parent)
        if parent not in (".", "/"):
            self.terminal(f"mkdir -p {parent}", timeout=10)

        # For small files, single command is fine
        chunk_size = 60_000  # ~60KB per chunk (well within shell limits)
        if len(b64) <= chunk_size:
            result = self.terminal(
                f"printf '%s' '{b64}' | base64 -d > {remote_path}",
                timeout=30,
            )
        else:
            # For larger files, write base64 in chunks then decode
            tmp_b64 = "/tmp/_kunming_upload.b64"
            self.terminal(f": > {tmp_b64}", timeout=5)  # truncate
            for i in range(0, len(b64), chunk_size):
                chunk = b64[i : i + chunk_size]
                self.terminal(f"printf '%s' '{chunk}' >> {tmp_b64}", timeout=15)
            result = self.terminal(
                f"base64 -d {tmp_b64} > {remote_path} && rm -f {tmp_b64}",
                timeout=30,
            )

        return result

    def upload_dir(self, local_dir: str, remote_dir: str) -> List[Dict[str, Any]]:
        """
        Upload an entire local directory to the rollout's sandbox (binary-safe).

        Recursively uploads all files, preserving directory structure.

        Args:
            local_dir: Path to a local directory on the host
            remote_dir: Destination directory inside the sandbox

        Returns:
            List of results, one per file uploaded
        """
        from pathlib import Path as _Path

        local = _Path(local_dir)
        if not local.exists() or not local.is_dir():
            return [{"exit_code": -1, "output": f"Local directory not found: {local_dir}"}]

        results = []
        for file_path in sorted(local.rglob("*")):
            if file_path.is_file():
                relative = file_path.relative_to(local)
                target = f"{remote_dir}/{relative}"
                results.append(self.upload_file(str(file_path), target))
        return results

    def download_file(self, remote_path: str, local_path: str) -> Dict[str, Any]:
        """
        Download a file from the rollout's sandbox to the host (binary-safe).

        The inverse of upload_file(). Base64-encodes the file inside the sandbox,
        reads the encoded data through the terminal, and decodes it locally.
        Safe for any file type.

        Args:
            remote_path: Path to the file inside the sandbox
            local_path: Destination path on the host

        Returns:
            Dict with 'success' (bool) and 'bytes' (int) or 'error' (str)
        """
        import base64
        from pathlib import Path as _Path

        # Read file as base64 inside the sandbox
        result = self.terminal(f"base64 '{remote_path}'", timeout=60)
        if result["exit_code"] != 0:
            return {"success": False, "error": result["output"]}

        # Decode and write locally
        try:
            decoded = base64.b64decode(result["output"])
            local = _Path(local_path)
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(decoded)
            return {"success": True, "bytes": len(decoded)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def download_dir(self, remote_dir: str, local_dir: str) -> List[Dict[str, Any]]:
        """
        Download an entire directory from the rollout's sandbox to the host.

        Recursively downloads all files, preserving directory structure.

        Args:
            remote_dir: Source directory inside the sandbox
            local_dir: Destination directory on the host

        Returns:
            List of results, one per file downloaded
        """
        from pathlib import Path as _Path

        # List all files recursively
        result = self.terminal(f"find '{remote_dir}' -type f", timeout=30)
        if result["exit_code"] != 0:
            return [{"success": False, "error": result["output"]}]

        files = [f for f in result["output"].split("\n") if f.strip()]
        results = []

        for remote_file in files:
            # Compute relative path and local destination
            rel_path = remote_file[len(remote_dir):].lstrip("/")
            local_path = _Path(local_dir) / rel_path
            results.append(self.download_file(remote_file, str(local_path)))

        return results

    def search(self, query: str, path: str = ".") -> Dict[str, Any]:
        """
        Search for patterns in the rollout's filesystem.

        Args:
            query: Search pattern (grep regex)
            path: Directory to search in

        Returns:
            Dict with search results
        """
        result = handle_function_call(
            "search_codebase",
            {"information_request": query, "target_directories": [path]},
            task_id=self.task_id,
        )
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"error": result}

    # -------------------------------------------------------------------------
    # Web tools
    # -------------------------------------------------------------------------

    def web_search(self, query: str, num_results: int = 5) -> Dict[str, Any]:
        """
        Search the web.

        Args:
            query: Search query
            num_results: Number of results to return

        Returns:
            Dict with search results
        """
        result = handle_function_call(
            "web_search", {"query": query, "num_results": num_results}, task_id=self.task_id
        )
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"error": result}

    def web_extract(self, urls: List[str]) -> Dict[str, Any]:
        """
        Extract content from URLs.

        Args:
            urls: List of URLs to extract

        Returns:
            Dict with extracted content
        """
        result = _run_tool_in_thread(
            "web_extract",
            {"urls": urls},
            self.task_id,
        )
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"error": result}

    # -------------------------------------------------------------------------
    # Browser tools
    # -------------------------------------------------------------------------

    def browser_navigate(self, url: str) -> Dict[str, Any]:
        """
        Navigate browser to a URL.

        Args:
            url: URL to navigate to

        Returns:
            Dict with navigation result
        """
        result = handle_function_call(
            "browser_navigate", {"url": url}, task_id=self.task_id
        )
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"error": result}

    def browser_click(self, selector: str) -> Dict[str, Any]:
        """
        Click an element on the page.

        Args:
            selector: CSS selector or XPath to click

        Returns:
            Dict with click result
        """
        result = handle_function_call(
            "browser_click", {"selector": selector}, task_id=self.task_id
        )
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"error": result}

    def browser_type(self, selector: str, text: str) -> Dict[str, Any]:
        """
        Type text into an element.

        Args:
            selector: CSS selector or XPath
            text: Text to type

        Returns:
            Dict with type result
        """
        result = handle_function_call(
            "browser_type", {"selector": selector, "text": text}, task_id=self.task_id
        )
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"error": result}

    def browser_scroll(self, direction: str = "down", amount: int = 300) -> Dict[str, Any]:
        """
        Scroll the page.

        Args:
            direction: 'up' or 'down'
            amount: Pixels to scroll

        Returns:
            Dict with scroll result
        """
        result = handle_function_call(
            "browser_scroll", {"direction": direction, "amount": amount}, task_id=self.task_id
        )
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"error": result}

    def browser_snapshot(self) -> Dict[str, Any]:
        """
        Get a snapshot of the current page.

        Returns:
            Dict with page content and interactive elements
        """
        result = handle_function_call(
            "browser_snapshot", {}, task_id=self.task_id
        )
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"error": result}

    # -------------------------------------------------------------------------
    # Generic tool access
    # -------------------------------------------------------------------------

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call any kunming-agent tool by name.

        This is the escape hatch -- if a specific method isn't implemented above,
        you can use this to call any tool directly.

        Args:
            tool_name: Name of the tool (e.g., "terminal", "read_file", "web_search")
            arguments: Dict of arguments to pass to the tool

        Returns:
            Dict with tool result
        """
        result = handle_function_call(tool_name, arguments, task_id=self.task_id)
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"result": result}

    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------

    def cleanup(self):
        """
        Clean up resources associated with this rollout.

        Called automatically after compute_reward() returns.
        """
        try:
            cleanup_vm(self.task_id)
        except Exception as e:
            logger.warning("Error cleaning up terminal for task %s: %s", self.task_id[:8], e)

        try:
            cleanup_browser(self.task_id)
        except Exception as e:
            logger.warning("Error cleaning up browser for task %s: %s", self.task_id[:8], e)
