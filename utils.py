"""Shared utility functions for kunming-agent."""

import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Union

import yaml


_CJK_RE = re.compile(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]')


def _extract_tokens(text: str) -> set:
    """Extract search tokens from text, supporting both Latin and CJK scripts.

    Returns a set of lowercase word tokens (Latin) plus individual CJK characters
    and bigrams for better recall matching across Chinese/Japanese/Korean text.
    """
    tokens = set(re.findall(r'[a-zA-Z][\w.-]+[\w]|\d+', text.lower()))
    cjk_chars = _CJK_RE.findall(text)
    tokens.update(cjk_chars)
    for i in range(len(cjk_chars) - 1):
        tokens.add(cjk_chars[i] + cjk_chars[i + 1])
    return tokens


TRUTHY_STRINGS = frozenset({"1", "true", "yes", "on"})


def is_truthy_value(value: Any, default: bool = False) -> bool:
    """Coerce bool-ish values using the project's shared truthy string set."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in TRUTHY_STRINGS
    return bool(value)


def env_var_enabled(name: str, default: str = "") -> bool:
    """Return True when an environment variable is set to a truthy value."""
    return is_truthy_value(os.getenv(name, default), default=False)


def atomic_json_write(
    path: Union[str, Path],
    data: Any,
    *,
    indent: int = 2,
    **dump_kwargs: Any,
) -> None:
    """Write JSON data to a file atomically.

    Uses temp file + fsync + os.replace to ensure the target file is never
    left in a partially-written state. If the process crashes mid-write,
    the previous version of the file remains intact.

    Args:
        path: Target file path (will be created or overwritten).
        data: JSON-serializable data to write.
        indent: JSON indentation (default 2).
        **dump_kwargs: Additional keyword args forwarded to json.dump(), such
            as default=str for non-native types.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.stem}_",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                indent=indent,
                ensure_ascii=False,
                **dump_kwargs,
            )
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        # Intentionally catch BaseException so temp-file cleanup still runs for
        # KeyboardInterrupt/SystemExit before re-raising the original signal.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def atomic_yaml_write(
    path: Union[str, Path],
    data: Any,
    *,
    default_flow_style: bool = False,
    sort_keys: bool = False,
    extra_content: str | None = None,
) -> None:
    """Write YAML data to a file atomically.

    Uses temp file + fsync + os.replace to ensure the target file is never
    left in a partially-written state.  If the process crashes mid-write,
    the previous version of the file remains intact.

    Args:
        path: Target file path (will be created or overwritten).
        data: YAML-serializable data to write.
        default_flow_style: YAML flow style (default False).
        sort_keys: Whether to sort dict keys (default False).
        extra_content: Optional string to append after the YAML dump
            (e.g. commented-out sections for user reference).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.stem}_",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=default_flow_style, sort_keys=sort_keys)
            if extra_content:
                f.write(extra_content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        # Match atomic_json_write: cleanup must also happen for process-level
        # interruptions before we re-raise them.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# Windows process detection helper
_IS_WINDOWS = os.name == "nt"


def is_process_running(pid: int) -> bool:
    """Check if a process with the given PID is currently running.

    Uses Windows-native API on Windows (via ctypes) to avoid SystemError
    from os.kill(pid, 0). Uses os.kill on Unix-like systems.

    Args:
        pid: Process ID to check.

    Returns:
        True if process exists and is running, False otherwise.
    """
    if _IS_WINDOWS:
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.windll.kernel32
            OpenProcess = kernel32.OpenProcess
            OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            OpenProcess.restype = wintypes.HANDLE
            CloseHandle = kernel32.CloseHandle
            CloseHandle.argtypes = [wintypes.HANDLE]
            CloseHandle.restype = wintypes.BOOL

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            hProcess = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not hProcess:
                return False
            CloseHandle(hProcess)
            return True
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)  # signal 0 = existence check, no actual signal sent
            return True
        except (ProcessLookupError, PermissionError, OSError):
            return False


# =============================================================================
# SimHash implementation for semantic similarity search
# =============================================================================


def simhash(text: str, hashbits: int = 64) -> int:
    """Compute simhash fingerprint for text using hash-based fingerprints.
    
    This implementation uses MD5 hashing to create a 64-bit fingerprint
    that can be used for fast semantic similarity comparison.
    
    Args:
        text: Input text to hash
        hashbits: Number of bits in the hash (default 64)
        
    Returns:
        Integer fingerprint value
    """
    if not text:
        return 0
    
    # Tokenize: CJK characters + word tokens
    cjk_re = re.compile(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]{1,}')
    tokens = []
    
    # Extract CJK characters
    for match in cjk_re.finditer(text):
        tokens.append(match.group())
    
    # Extract word tokens
    words = re.findall(r'[a-zA-Z]+', text.lower())
    tokens.extend(words)
    
    if not tokens:
        return 0
    
    # Compute weighted hash
    v = [0] * hashbits
    for token in tokens:
        # Use MD5 for consistent hashing
        hash_val = int(hashlib.md5(token.encode('utf-8')).hexdigest(), 16)
        for i in range(hashbits):
            bit = (hash_val >> i) & 1
            if bit:
                v[i] += 1
            else:
                v[i] -= 1
    
    # Build fingerprint
    fingerprint = 0
    for i in range(hashbits):
        if v[i] > 0:
            fingerprint |= (1 << i)
    
    return fingerprint


def simhash_similarity(hash1: int, hash2: int, hashbits: int = 64) -> float:
    """Calculate similarity between two simhash fingerprints.
    
    Uses Hamming distance to compute similarity. Returns a value between
    0.0 (completely different) and 1.0 (identical).
    
    Args:
        hash1: First fingerprint
        hash2: Second fingerprint
        hashbits: Number of bits in the hash (default 64)
        
    Returns:
        Similarity score between 0.0 and 1.0
    """
    if hash1 == hash2:
        return 1.0
    
    # Compute Hamming distance
    xor = hash1 ^ hash2
    distance = 0
    while xor:
        distance += xor & 1
        xor >>= 1
    
    # Convert to similarity (1.0 = identical, 0.0 = max distance)
    return 1.0 - (distance / hashbits)


# =============================================================================
# Cross-platform file locking
# =============================================================================


@contextmanager
def file_lock(lock_path: Union[str, Path], timeout: float = 10.0) -> Generator[bool, None, None]:
    """Cross-platform file lock context manager.
    
    Uses fcntl on Unix-like systems and msvcrt on Windows.
    Falls back to a simple timeout-based lock if neither is available.
    
    Args:
        lock_path: Path to the lock file
        timeout: Maximum time to wait for lock in seconds (default 10.0)
        
    Yields:
        True if lock was acquired, False otherwise
        
    Example:
        with file_lock("/tmp/my_lock", timeout=5.0) as acquired:
            if acquired:
                # Do protected work
                pass
    """
    import time
    
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    
    lock_file = None
    acquired = False
    
    try:
        # Try to acquire lock with timeout
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                if os.name == 'nt':  # Windows
                    import msvcrt
                    lock_file = open(lock_path, 'w')
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    acquired = True
                    break
                else:  # Unix-like
                    import fcntl
                    lock_file = open(lock_path, 'w')
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
            except (IOError, OSError, ImportError):
                # Lock not available, wait and retry
                time.sleep(0.1)
        
        yield acquired
        
    finally:
        if lock_file:
            try:
                if os.name == 'nt' and acquired:
                    import msvcrt
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                elif acquired:
                    import fcntl
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            finally:
                lock_file.close()
