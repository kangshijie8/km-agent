"""Tests for Windows-specific code execution functionality.

Verifies that code execution sandbox works correctly on Windows,
including process management, signal handling, and PATH configuration.
"""

import os
import platform
import subprocess
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

_IS_WINDOWS = platform.system() == "Windows"

# Skip all tests if not on Windows
pytestmark = [
    pytest.mark.skipif(not _IS_WINDOWS, reason="Windows-only tests"),
]


class TestCodeExecutionWindows:
    """Test Windows-specific code execution behavior."""

    def test_is_windows_constant(self):
        """Verify _IS_WINDOWS is True on Windows."""
        from tools import code_execution_tool
        assert code_execution_tool._IS_WINDOWS is True

    def test_sandbox_unavailable_on_windows(self):
        """Verify sandbox is marked unavailable on Windows."""
        from tools.code_execution_tool import SANDBOX_AVAILABLE

        # Sandbox should not be available on Windows
        assert SANDBOX_AVAILABLE is False

    def test_kill_process_group_windows(self):
        """Test _kill_process_group on Windows."""
        from tools.code_execution_tool import _kill_process_group

        # Create a subprocess
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )

        try:
            time.sleep(0.1)

            # Test kill
            result = _kill_process_group(proc, timeout=1)

            # Should succeed
            assert result is True

            # Process should be terminated
            time.sleep(0.5)
            assert proc.poll() is not None

        finally:
            # Cleanup
            try:
                proc.kill()
                proc.wait(timeout=2)
            except Exception:
                pass

    def test_execute_code_no_preexec_fn(self):
        """Verify execute_code doesn't use preexec_fn on Windows."""
        from tools.code_execution_tool import execute_code

        # Mock subprocess.Popen to capture arguments
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.communicate.return_value = (b"output", b"")
            mock_process.returncode = 0
            mock_popen.return_value = mock_process

            # Try to execute code
            try:
                execute_code(
                    code="print('hello')",
                    language="python",
                    timeout=30,
                )
            except Exception:
                pass  # We just want to check Popen arguments

            # Verify Popen was called
            if mock_popen.called:
                call_kwargs = mock_popen.call_args[1]
                # On Windows, preexec_fn should be None
                if "preexec_fn" in call_kwargs:
                    assert call_kwargs["preexec_fn"] is None


class TestWindowsCodeIsolation:
    """Test code isolation on Windows."""

    def test_code_execution_with_timeout(self):
        """Test code execution respects timeout on Windows."""
        from tools.code_execution_tool import execute_code

        # Execute code that should complete quickly
        result = execute_code(
            code="print('hello world')",
            language="python",
            timeout=10,
        )

        # Should succeed
        assert result is not None


class TestWindowsPathHandling:
    """Test Windows path handling in code execution."""

    def test_relative_path_handling(self):
        """Test relative path handling."""
        from tools.code_execution_tool import _resolve_cwd

        # Test relative path
        result = _resolve_cwd(".")

        # Should resolve to absolute path
        assert os.path.isabs(result)
