"""Retry utilities — jittered backoff for decorrelated retries.

Replaces fixed exponential backoff with jittered delays to prevent
thundering-herd retry spikes when multiple sessions hit the same
rate-limited provider concurrently.
"""

import random
import threading
import time

# Monotonic counter for jitter seed uniqueness within the same process.
# Protected by a lock to avoid race conditions in concurrent retry paths
# (e.g. multiple gateway sessions retrying simultaneously).
_jitter_counter = 0
_jitter_lock = threading.Lock()


def jittered_backoff(
    attempt: int,
    *,
    base_delay: float = 5.0,
    max_delay: float = 120.0,
    jitter_ratio: float = 0.5,
) -> float:
    """Compute a decorrelated jittered backoff delay.

    修复：更新文档以匹配实际实现（decorrelated jitter策略），
    原文档描述的 base * 2^(attempt-1) + jitter 与实际 uniform(base_delay, delay*3) 不一致。

    Args:
        attempt: 1-based retry attempt number.
        base_delay: Base delay in seconds (minimum delay floor).
        max_delay: Maximum delay cap in seconds.
        jitter_ratio: Unused in current implementation (kept for API
            compatibility). Previously controlled jitter range ratio.

    Returns:
        Delay in seconds: uniform(base_delay, min(base * 2^(attempt-1), max_delay) * 3),
        capped at max_delay. This is a decorrelated jitter strategy that spreads
        retries more effectively than simple exponential backoff + additive jitter.

    The decorrelated jitter decorrelates concurrent retries so multiple sessions
    hitting the same provider don't all retry at the same instant.
    """
    global _jitter_counter
    with _jitter_lock:
        _jitter_counter += 1
        tick = _jitter_counter

    exponent = max(0, attempt - 1)
    if exponent >= 63 or base_delay <= 0:
        delay = max_delay
    else:
        delay = min(base_delay * (2 ** exponent), max_delay)

    # Seed from time + counter for decorrelation even with coarse clocks.
    seed = (time.time_ns() ^ (tick * 0x9E3779B9)) & 0xFFFFFFFF
    rng = random.Random(seed)
    # Use decorrelated jitter: range is [base_delay, delay * 3] to better spread retries
    jittered = rng.uniform(base_delay, delay * 3)

    return min(jittered, max_delay)
