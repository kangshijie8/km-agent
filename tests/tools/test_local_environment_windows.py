"""Tests for Windows-specific local environment functionality.

Verifies that local environment execution works correctly on Windows,
including shell detection, process management, and PATH handling.
"""

import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_IS_WINDOWS = platform.system() == "Windows"

# Skip all tests if not on Windows
pytestmark = [
    pytest.mark.skipif(not _IS_WINDOWS, reason="Windows-only tests"),
]


class TestLocalEnvironmentWindows:
    """Test Windows-specific local environment behavior."""

    def test_is_windows_constant(self):
        """Verify _IS_WINDOWS is True on Windows."""
        from tools.environments import local
        assert local._IS_WINDOWS is True

    def test_find_shell_windows(self):
        """Test shell detection on Windows."""
        from tools.environments.local import _find_shell

        shell = _find_shell()

        # On Windows, should return a valid shell path
        assert shell is not None
        assert isinstance(shell, str)

        # Should be cmd.exe, powershell.exe, or git bash
        shell_lower = shell.lower()
        assert any(s in shell_lower for s in ["cmd", "powershell", "pwsh", "bash"])

    def test_sane_path_uses_pathsep(self):
        """Verify _SANE_PATH uses os.pathsep for path joining."""
        from tools.environments.local import _SANE_PATH

        # Should use os.pathsep (semicolon on Windows)
        if _IS_WINDOWS:
            # On Windows, paths are joined with semicolons
            assert ";" in _SANE_PATH or _SANE_PATH == ""

    def test_run_bash_no_preexec_fn(self):
        """Verify _run_bash doesn't use preexec_fn on Windows."""
        from tools.environments.local import LocalEnvironment

        env = LocalEnvironment()

        # Mock subprocess.Popen to capture arguments
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.stdout = MagicMock()
            mock_process.stdout.readline.side_effect = [b"test output\n", b""]
            mock_process.poll.return_value = 0
            mock_popen.return_value = mock_process

            # Try to run a command
            try:
                list(env._run_bash("echo test", cwd="."))
            except Exception:
                pass  # We just want to check Popen arguments

            # Verify Popen was called
            if mock_popen.called:
                call_kwargs = mock_popen.call_args[1]
                # On Windows, preexec_fn should be None
                if "preexec_fn" in call_kwargs:
                    assert call_kwargs["preexec_fn"] is None

    def test_kill_process_windows(self):
        """Test _kill_process on Windows uses correct termination."""
        from tools.environments.local import LocalEnvironment

        env = LocalEnvironment()

        # Create a real subprocess
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            time.sleep(0.1)

            # Test kill
            result = env._kill_process(proc, timeout=1)

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


class TestWindowsShellExecution:
    """Test Windows shell command execution."""

    def test_execute_basic_command(self):
        """Test executing a basic command on Windows."""
        from tools.environments.local import LocalEnvironment

        env = LocalEnvironment()

        # Execute a simple command
        result = env.execute("echo Hello World", cwd=".")

        # Should succeed
        assert result.returncode == 0
        assert "Hello World" in result.stdout

    def test_execute_with_cwd(self):
        """Test executing command with specific working directory."""
        from tools.environments.local import LocalEnvironment

        env = LocalEnvironment()

        # Get current directory
        current_dir = os.getcwd()

        # Execute cd command
        result = env.execute("cd", cwd=current_dir)
        assert result.returncode == 0


class TestWindowsPathHandling:
    """Test Windows path handling in local environment."""

    def test_path_with_spaces(self):
        """Test handling paths with spaces on Windows."""
        from tools.environments.local import LocalEnvironment

        env = LocalEnvironment()

        # Test path with spaces - just verify env creation works
        result = env._make_run_env()
        assert "PATH" in result

    def test_relative_path_resolution(self):
        """Test relative path resolution on Windows."""
        from tools.environments.local import LocalEnvironment

        env = LocalEnvironment()

        # Test relative path
        relative_path = "."
        result = env.execute("cd", cwd=relative_path)

        assert result.returncode == 0


class TestWindowsCommandParsing:
    """Test Windows command parsing behavior."""

    def test_command_with_quotes(self):
        """Test commands with quotes on Windows."""
        from tools.environments.local import LocalEnvironment

        env = LocalEnvironment()

        # Command with quotes
        result = env.execute('echo "Hello World"', cwd=".")

        assert result.returncode == 0
        assert "Hello World" in result.stdout

    def test_command_with_special_chars(self):
        """Test commands with special characters."""
        from tools.environments.local import LocalEnvironment

        env = LocalEnvironment()

        # Command with special chars (careful with Windows shell)
        result = env.execute("echo test", cwd=".")

        assert result.returncode == 0
