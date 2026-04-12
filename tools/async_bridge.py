"""Async bridging utilities for tool handlers.

Provides a single source of truth for running async coroutines from sync contexts.
This module is separate to avoid circular imports between registry and model_tools.
"""

import asyncio
import threading
from typing import Any

# Persistent loop for the main (CLI) thread
_tool_loop = None
_tool_loop_lock = threading.Lock()

# Per-worker-thread persistent loops
_worker_thread_local = threading.local()


def _get_tool_loop():
    """Return a long-lived event loop for running async tool handlers.

    Using a persistent loop (instead of asyncio.run() which creates and
    *closes* a fresh loop every time) prevents "Event loop is closed"
    errors that occur when cached httpx/AsyncOpenAI clients attempt to
    close their transport on a dead loop during garbage collection.
    """
    global _tool_loop
    with _tool_loop_lock:
        if _tool_loop is None or _tool_loop.is_closed():
            _tool_loop = asyncio.new_event_loop()
        return _tool_loop


def _get_worker_loop():
    """Return a persistent event loop for the current worker thread.

    Each worker thread gets its own long-lived loop stored in thread-local
    storage. This prevents the "Event loop is closed" errors that occurred
    when asyncio.run() was used per-call.
    """
    loop = getattr(_worker_thread_local, 'loop', None)
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _worker_thread_local.loop = loop
    return loop


def run_async(coro) -> Any:
    """Run an async coroutine from a sync context.

    If the current thread already has a running event loop (e.g., inside
    the gateway's async stack), we spin up a disposable thread so
    asyncio.run() can create its own loop without conflicting.

    For the common CLI path (no running loop), we use a persistent event
    loop so that cached async clients remain bound to a live loop.

    When called from a worker thread, we use a per-thread persistent loop
    to avoid both contention with the main thread's shared loop AND the
    "Event loop is closed" errors.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Inside an async context - run in a fresh thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=300)

    # If we're on a worker thread, use a per-thread persistent loop
    if threading.current_thread() is not threading.main_thread():
        worker_loop = _get_worker_loop()
        return worker_loop.run_until_complete(coro)

    tool_loop = _get_tool_loop()
    return tool_loop.run_until_complete(coro)
