"""
Delivery routing for cron job outputs and agent responses.

Routes messages to the appropriate destination based on:
- Explicit targets (e.g., "telegram:123456789")
- Platform home channels (e.g., "telegram" home channel)
- Origin (back to where the job was created)
- Local (always saved to files)
"""

import logging
import os
import random
import tempfile
import time
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Union, Callable

from kunming_cli.config import get_kunming_home

logger = logging.getLogger(__name__)

MAX_PLATFORM_OUTPUT = 4000
TRUNCATED_VISIBLE = 3800

# Retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0  # seconds
DEFAULT_MAX_DELAY = 60.0  # seconds


def _exponential_backoff_with_jitter(
    attempt: int,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
) -> float:
    """
    Calculate delay with exponential backoff and jitter.
    
    Formula: delay = min(base_delay * (2 ** attempt), max_delay) + jitter
    Jitter is a random value between 0 and base_delay to avoid thundering herd.
    """
    exponential_delay = min(base_delay * (2 ** attempt), max_delay)
    jitter = random.uniform(0, base_delay)
    return exponential_delay + jitter


def _retry_with_backoff(
    operation: Callable,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    task_id: Optional[str] = None,
) -> Any:
    """
    Execute an operation with exponential backoff retry logic.
    
    Args:
        operation: Callable to execute (should raise on failure)
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        task_id: Optional task ID for logging
    
    Returns:
        Result of the operation
    
    Raises:
        Exception: The last exception after all retries are exhausted
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return operation()
        except Exception as e:
            last_exception = e
            
            if attempt >= max_retries:
                logger.error(
                    "[delivery] Operation failed after %d retries%s: %s",
                    max_retries,
                    f" (task: {task_id})" if task_id else "",
                    str(e),
                )
                raise last_exception
            
            delay = _exponential_backoff_with_jitter(attempt, base_delay, max_delay)
            logger.warning(
                "[delivery] Operation failed (attempt %d/%d)%s: %s. Retrying in %.2fs...",
                attempt + 1,
                max_retries + 1,
                f" (task: {task_id})" if task_id else "",
                str(e),
                delay,
            )
            time.sleep(delay)
    
    # This should never be reached, but just in case
    raise last_exception if last_exception else RuntimeError("Unknown error in retry logic")

from .config import Platform, GatewayConfig
from .session import SessionSource


@dataclass
class DeliveryTarget:
    """
    A single delivery target.
    
    Represents where a message should be sent:
    - "origin" back to source
    - "local" save to local files
    - "telegram" Telegram home channel
    - "telegram:123456" specific Telegram chat
    """
    platform: Platform
    chat_id: Optional[str] = None  # None means use home channel
    thread_id: Optional[str] = None
    is_origin: bool = False
    is_explicit: bool = False  # True if chat_id was explicitly specified
    
    @classmethod
    def parse(cls, target: str, origin: Optional[SessionSource] = None) -> "DeliveryTarget":
        """
        Parse a delivery target string.
        
        Formats:
        - "origin" back to source
        - "local" local files only
        - "telegram" Telegram home channel
        - "telegram:123456" specific Telegram chat
        """
        target = target.strip().lower()
        
        if target == "origin":
            if origin:
                return cls(
                    platform=origin.platform,
                    chat_id=origin.chat_id,
                    thread_id=origin.thread_id,
                    is_origin=True,
                )
            else:
                # Fallback to local if no origin
                return cls(platform=Platform.LOCAL, is_origin=True)
        
        if target == "local":
            return cls(platform=Platform.LOCAL)
        
        # Check for platform:chat_id or platform:chat_id:thread_id format
        if ":" in target:
            parts = target.split(":", 2)
            platform_str = parts[0]
            chat_id = parts[1] if len(parts) > 1 else None
            thread_id = parts[2] if len(parts) > 2 else None
            try:
                platform = Platform(platform_str)
                return cls(platform=platform, chat_id=chat_id, thread_id=thread_id, is_explicit=True)
            except ValueError:
                # Unknown platform, treat as local
                return cls(platform=Platform.LOCAL)
        
        # Just a platform name (use home channel)
        try:
            platform = Platform(target)
            return cls(platform=platform)
        except ValueError:
            # Unknown platform, treat as local
            return cls(platform=Platform.LOCAL)
    
    def to_string(self) -> str:
        """Convert back to string format."""
        if self.is_origin:
            return "origin"
        if self.platform == Platform.LOCAL:
            return "local"
        if self.chat_id and self.thread_id:
            return f"{self.platform.value}:{self.chat_id}:{self.thread_id}"
        if self.chat_id:
            return f"{self.platform.value}:{self.chat_id}"
        return self.platform.value


class DeliveryRouter:
    """
    Routes messages to appropriate destinations.
    
    Handles the logic of resolving delivery targets and dispatching
    messages to the right platform adapters.
    """
    
    def __init__(self, config: GatewayConfig, adapters: Dict[Platform, Any] = None):
        """
        Initialize the delivery router.
        
        Args:
            config: Gateway configuration
            adapters: Dict mapping platforms to their adapter instances
        """
        self.config = config
        self.adapters = adapters or {}
        self.output_dir = get_kunming_home() / "cron" / "output"
    
    def resolve_targets(
        self,
        deliver: Union[str, List[str]],
        origin: Optional[SessionSource] = None
    ) -> List[DeliveryTarget]:
        """
        Resolve delivery specification to concrete targets.
        
        Args:
            deliver: Delivery spec - "origin", "telegram", ["local", "discord"], etc.
            origin: The source where the request originated (for "origin" target)
        
        Returns:
            List of resolved delivery targets
        """
        if isinstance(deliver, str):
            deliver = [deliver]
        
        targets = []
        seen_platforms = set()
        
        for target_str in deliver:
            target = DeliveryTarget.parse(target_str, origin)
            
            # Resolve home channel if needed
            if target.chat_id is None and target.platform != Platform.LOCAL:
                home = self.config.get_home_channel(target.platform)
                if home:
                    target.chat_id = home.chat_id
                else:
                    # No home channel configured, skip this platform
                    continue
            
            # Deduplicate
            key = (target.platform, target.chat_id, target.thread_id)
            if key not in seen_platforms:
                seen_platforms.add(key)
                targets.append(target)
        
        # Always include local if configured
        if self.config.always_log_local:
            local_key = (Platform.LOCAL, None, None)
            if local_key not in seen_platforms:
                targets.append(DeliveryTarget(platform=Platform.LOCAL))
        
        return targets
    
    async def deliver(
        self,
        content: str,
        targets: List[DeliveryTarget],
        job_id: Optional[str] = None,
        job_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Deliver content to all specified targets.
        
        Args:
            content: The message/output to deliver
            targets: List of delivery targets
            job_id: Optional job ID (for cron jobs)
            job_name: Optional job name
            metadata: Additional metadata to include
        
        Returns:
            Dict with delivery results per target
        """
        results = {}
        
        for target in targets:
            try:
                if target.platform == Platform.LOCAL:
                    result = self._deliver_local(content, job_id, job_name, metadata)
                else:
                    result = await self._deliver_to_platform(target, content, metadata)
                
                results[target.to_string()] = {
                    "success": True,
                    "result": result
                }
            except Exception as e:
                results[target.to_string()] = {
                    "success": False,
                    "error": str(e)
                }
        
        return results
    
    def _deliver_local(
        self,
        content: str,
        job_id: Optional[str],
        job_name: Optional[str],
        metadata: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Save content to local files with atomic write and retry logic."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if job_id:
            output_path = self.output_dir / job_id / f"{timestamp}.md"
        else:
            output_path = self.output_dir / "misc" / f"{timestamp}.md"
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Build the output document
        lines = []
        if job_name:
            lines.append(f"# {job_name}")
        else:
            lines.append("# Delivery Output")
        
        lines.append("")
        lines.append(f"**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        if job_id:
            lines.append(f"**Job ID:** {job_id}")
        
        if metadata:
            for key, value in metadata.items():
                lines.append(f"**{key}:** {value}")
        
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(content)
        
        content_str = "\n".join(lines)
        
        # Atomic write with retry logic
        def _atomic_write():
            # Create a temporary file in the same directory for atomic rename
            fd, tmp_path = tempfile.mkstemp(
                dir=str(output_path.parent),
                suffix=".tmp",
                prefix=f".{output_path.stem}_",
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(content_str)
                    f.flush()
                    os.fsync(f.fileno())
                # Atomic replace: this is guaranteed to be atomic on POSIX and Windows
                os.replace(tmp_path, output_path)
            except BaseException:
                # Clean up temp file on any failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        
        # Execute with retry logic
        _retry_with_backoff(
            operation=_atomic_write,
            max_retries=DEFAULT_MAX_RETRIES,
            base_delay=DEFAULT_BASE_DELAY,
            max_delay=DEFAULT_MAX_DELAY,
            task_id=job_id,
        )
        
        return {
            "path": str(output_path),
            "timestamp": timestamp
        }
    
    def _save_full_output(self, content: str, job_id: str) -> Path:
        """Save full cron output to disk and return the file path."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = get_kunming_home() / "cron" / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{job_id}_{timestamp}.txt"
        path.write_text(content)
        return path

    async def _deliver_to_platform(
        self,
        target: DeliveryTarget,
        content: str,
        metadata: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Deliver content to a messaging platform with retry logic."""
        adapter = self.adapters.get(target.platform)
        
        if not adapter:
            raise ValueError(f"No adapter configured for {target.platform.value}")
        
        if not target.chat_id:
            raise ValueError(f"No chat ID for {target.platform.value} delivery")
        
        # Guard: truncate oversized cron output to stay within platform limits
        if len(content) > MAX_PLATFORM_OUTPUT:
            job_id = (metadata or {}).get("job_id", "unknown")
            saved_path = self._save_full_output(content, job_id)
            logger.info("Cron output truncated (%d chars) full output: %s", len(content), saved_path)
            content = (
                content[:TRUNCATED_VISIBLE]
                + f"\n\n... [truncated, full output saved to {saved_path}]"
            )
        
        send_metadata = dict(metadata or {})
        if target.thread_id and "thread_id" not in send_metadata:
            send_metadata["thread_id"] = target.thread_id
        
        # Async retry wrapper for platform delivery
        return await self._retry_async_with_backoff(
            operation=lambda: adapter.send(target.chat_id, content, metadata=send_metadata or None),
            max_retries=DEFAULT_MAX_RETRIES,
            base_delay=DEFAULT_BASE_DELAY,
            max_delay=DEFAULT_MAX_DELAY,
            task_id=(metadata or {}).get("job_id"),
        )

    async def _deliver_webhook(
        self,
        webhook_url: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Deliver content to a webhook endpoint with retry logic.
        
        Args:
            webhook_url: The webhook URL to send to
            content: The content to send
            metadata: Additional metadata to include in the payload
            headers: Optional custom headers
        
        Returns:
            Dict with delivery result
        """
        import aiohttp
        
        payload = {
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }
        if metadata:
            payload.update(metadata)
        
        default_headers = {
            "Content-Type": "application/json",
        }
        if headers:
            default_headers.update(headers)
        
        async def _send_request():
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    webhook_url,
                    json=payload,
                    headers=default_headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    response.raise_for_status()
                    return {
                        "status": response.status,
                        "webhook_url": webhook_url,
                    }
        
        return await self._retry_async_with_backoff(
            operation=_send_request,
            max_retries=DEFAULT_MAX_RETRIES,
            base_delay=DEFAULT_BASE_DELAY,
            max_delay=DEFAULT_MAX_DELAY,
            task_id=(metadata or {}).get("job_id"),
        )

    async def _retry_async_with_backoff(
        self,
        operation: Callable,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_delay: float = DEFAULT_BASE_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        task_id: Optional[str] = None,
    ) -> Any:
        """
        Execute an async operation with exponential backoff retry logic.
        
        Args:
            operation: Async callable to execute (should raise on failure)
            max_retries: Maximum number of retry attempts
            base_delay: Initial delay in seconds
            max_delay: Maximum delay in seconds
            task_id: Optional task ID for logging
        
        Returns:
            Result of the operation
        
        Raises:
            Exception: The last exception after all retries are exhausted
        """
        import asyncio
        
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                return await operation()
            except Exception as e:
                last_exception = e
                
                if attempt >= max_retries:
                    logger.error(
                        "[delivery] Async operation failed after %d retries%s: %s",
                        max_retries,
                        f" (task: {task_id})" if task_id else "",
                        str(e),
                    )
                    raise last_exception
                
                delay = _exponential_backoff_with_jitter(attempt, base_delay, max_delay)
                logger.warning(
                    "[delivery] Async operation failed (attempt %d/%d)%s: %s. Retrying in %.2fs...",
                    attempt + 1,
                    max_retries + 1,
                    f" (task: {task_id})" if task_id else "",
                    str(e),
                    delay,
                )
                await asyncio.sleep(delay)
        
        # This should never be reached, but just in case
        raise last_exception if last_exception else RuntimeError("Unknown error in async retry logic")


def parse_deliver_spec(
    deliver: Optional[Union[str, List[str]]],
    origin: Optional[SessionSource] = None,
    default: str = "origin"
) -> Union[str, List[str]]:
    """
    Normalize a delivery specification.
    
    If None or empty, returns the default.
    """
    if not deliver:
        return default
    return deliver



