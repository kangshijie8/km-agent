"""
Async Bridge — 同步代码与异步代码的桥接层。

参考 openakita 的 engine_bridge.py 设计，为 kunming-agent 提供：
1. 后台 asyncio 事件循环（在独立线程运行）
2. 同步代码调用异步协程的接口
3. 流式异步生成器的同步包装

核心解决的问题：
- Windows 上同步线程模型 + GIL 导致的阻塞无法中断问题
- 使用 asyncio.Event 竞速模式实现即时响应的中断
- 避免 C 扩展 socket.recv() 阻塞导致的 AGENT_THREAD_STUCK

Usage:
    from agent.async_bridge import run_async, stream_async
    
    # 调用异步函数并等待结果
    result = run_async(my_async_function())
    
    # 流式异步生成器
    for chunk in stream_async(my_async_generator()):
        print(chunk)
"""

from __future__ import annotations

import asyncio
import logging
import queue as stdlib_queue
import threading
import time
from collections.abc import AsyncIterator, Coroutine, Generator
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# 全局事件循环（在后台线程运行）
_bridge_loop: asyncio.AbstractEventLoop | None = None
_bridge_thread: threading.Thread | None = None
_bridge_lock = threading.Lock()

# 流式桥接的哨兵对象
_STREAM_DONE = object()
_STREAM_ERROR = "__ASYNC_BRIDGE_STREAM_ERROR__"


def _ensure_bridge_loop() -> asyncio.AbstractEventLoop:
    """确保后台事件循环已启动，返回 loop 引用。"""
    global _bridge_loop, _bridge_thread
    
    with _bridge_lock:
        if _bridge_loop is not None and _bridge_loop.is_running():
            return _bridge_loop
        
        # 创建新的事件循环
        _bridge_loop = asyncio.new_event_loop()
        
        def _run_loop():
            """在后台线程运行事件循环。"""
            asyncio.set_event_loop(_bridge_loop)
            try:
                _bridge_loop.run_forever()
            except Exception as exc:
                logger.error("Bridge loop error: %s", exc)
            finally:
                try:
                    _bridge_loop.close()
                except Exception:
                    pass
        
        _bridge_thread = threading.Thread(target=_run_loop, daemon=True, name="async-bridge-loop")
        _bridge_thread.start()
        
        # 等待循环启动
        for _ in range(50):  # 最多等 5 秒
            if _bridge_loop.is_running():
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("Failed to start async bridge loop")
        
        logger.info("Async bridge loop started (thread=%s)", _bridge_thread.ident)
        return _bridge_loop


def run_async(coro: Coroutine[Any, Any, T], timeout: float | None = None) -> T:
    """
    在后台事件循环中运行协程，同步等待结果。
    
    这是同步代码调用异步函数的主要入口。
    
    Args:
        coro: 要运行的协程
        timeout: 超时时间（秒），None 表示不超时
        
    Returns:
        协程的返回值
        
    Raises:
        TimeoutError: 如果超时
        Exception: 协程中抛出的异常
    """
    loop = _ensure_bridge_loop()
    
    # 提交协程到后台循环
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    
    # 同步等待结果
    try:
        return future.result(timeout=timeout)
    except Exception:
        # 确保取消未完成的 future
        if not future.done():
            future.cancel()
        raise


def stream_async(async_gen: AsyncIterator[T], timeout: float | None = None) -> Generator[T, None, None]:
    """
    将异步生成器桥接为同步生成器。
    
    用于流式响应（如 SSE、chunked response）的同步消费。
    
    Args:
        async_gen: 异步生成器
        timeout: 每次获取的超时时间（秒）
        
    Yields:
        生成器的每个值
        
    Example:
        async def my_async_gen():
            for i in range(10):
                await asyncio.sleep(0.1)
                yield i
        
        for value in stream_async(my_async_gen()):
            print(value)  # 同步代码中使用
    """
    loop = _ensure_bridge_loop()
    buf: stdlib_queue.Queue[Any] = stdlib_queue.Queue(maxsize=512)
    
    async def _pump():
        """在后台循环中泵送异步生成器的值到队列。"""
        try:
            async for item in async_gen:
                buf.put(item)
        except Exception as exc:
            buf.put((_STREAM_ERROR, exc))
        finally:
            buf.put(_STREAM_DONE)
    
    # 启动泵送任务
    future = asyncio.run_coroutine_threadsafe(_pump(), loop)
    
    try:
        while True:
            try:
                item = buf.get(timeout=timeout)
            except stdlib_queue.Empty:
                raise TimeoutError(f"Stream item wait timeout ({timeout}s)")
            
            if item is _STREAM_DONE:
                break
            
            if isinstance(item, tuple) and len(item) == 2 and item[0] == _STREAM_ERROR:
                raise item[1]
            
            yield item
    finally:
        # 确保取消未完成的任务
        if not future.done():
            future.cancel()


async def cancellable_coroutine(
    coro: Coroutine[Any, Any, T],
    cancel_event: asyncio.Event,
) -> T:
    """
    将协程包装为可取消的，使用 cancel_event 竞速模式。
    
    这是实现即时中断的核心函数。当 cancel_event 被 set() 时，
    无论协程执行到何处，都会立即抛出 CancelledError。
    
    Args:
        coro: 要运行的协程
        cancel_event: 取消事件信号
        
    Returns:
        协程的返回值
        
    Raises:
        asyncio.CancelledError: 如果 cancel_event 先触发
        Exception: 协程中抛出的其他异常
    """
    task = asyncio.create_task(coro)
    cancel_waiter = asyncio.create_task(cancel_event.wait())
    
    done, pending = await asyncio.wait(
        {task, cancel_waiter},
        return_when=asyncio.FIRST_COMPLETED,
    )
    
    # 取消未完成的任务
    for t in pending:
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass
    
    if task in done:
        return task.result()
    else:
        # cancel_event 先触发
        raise asyncio.CancelledError("Operation cancelled by user")


def shutdown_bridge():
    """关闭桥接层，清理资源。"""
    global _bridge_loop, _bridge_thread
    
    with _bridge_lock:
        if _bridge_loop is not None:
            try:
                _bridge_loop.call_soon_threadsafe(_bridge_loop.stop)
            except Exception:
                pass
            _bridge_loop = None
        
        if _bridge_thread is not None:
            _bridge_thread.join(timeout=5)
            _bridge_thread = None
        
        logger.info("Async bridge shutdown")


# 兼容性：旧代码可能直接导入这些
__all__ = [
    "run_async",
    "stream_async",
    "cancellable_coroutine",
    "shutdown_bridge",
]
