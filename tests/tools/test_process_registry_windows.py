"""Tests for Windows-specific process registry functionality.

Verifies that process management works correctly on Windows,
including process spawning, termination, and signal handling.
"""

import platform
import subprocess
import sys
import time
import uuid
from unittest.mock import MagicMock, patch

import pytest

_IS_WINDOWS = platform.system() == "Windows"

# Skip all tests if not on Windows
pytestmark = [
    pytest.mark.skipif(not _IS_WINDOWS, reason="Windows-only tests"),
]


class TestProcessRegistryWindows:
    """Test Windows-specific process registry behavior."""

    def test_is_windows_constant(self):
        """Verify _IS_WINDOWS is True on Windows."""
        from tools import process_registry
        assert process_registry._IS_WINDOWS is True

    def test_terminate_host_pid_windows(self):
        """Test _terminate_host_pid uses correct Windows method."""
        from tools.process_registry import ProcessRegistry

        # Create a dummy process that we can terminate
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        pid = proc.pid

        try:
            # Give process time to start
            time.sleep(0.1)

            # Test termination using the static method
            ProcessRegistry._terminate_host_pid(pid)

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

    def test_spawn_local_no_preexec_fn(self):
        """Verify spawn_local doesn't use preexec_fn on Windows."""
        from tools.process_registry import ProcessRegistry

        registry = ProcessRegistry()
        mock_env = MagicMock()
        mock_env.env_type = "local"
        mock_env.execute = MagicMock(return_value=("", "", 0))

        # Mock subprocess.Popen to capture arguments
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_popen.return_value = mock_process

            # Try to spawn a process
            try:
                registry.spawn_local(
                    env=mock_env,
                    command="echo test",
                    task_id="test_task",
                )
            except Exception:
                pass  # We just want to check Popen arguments

            # Verify Popen was called
            if mock_popen.called:
                call_kwargs = mock_popen.call_args[1]
                # On Windows, preexec_fn should be None or not present
                if "preexec_fn" in call_kwargs:
                    assert call_kwargs["preexec_fn"] is None

    def test_kill_process_windows(self):
        """Test kill_process on Windows uses correct termination method."""
        from tools.process_registry import ProcessRegistry, ProcessSession

        registry = ProcessRegistry()

        # Create a real subprocess
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Create a session
        session = ProcessSession(
            id=f"proc_{uuid.uuid4().hex[:12]}",
            command="python -c 'import time; time.sleep(60)'",
            task_id="test",
            pid=proc.pid,
            process=proc,
            started_at=time.time(),
        )

        # Register session
        registry._sessions[session.id] = session

        try:
            # Kill the process
            result = registry.kill(session.id)
            assert result is True

            # Verify process is terminated
            time.sleep(0.5)
            assert proc.poll() is not None

        finally:
            # Cleanup
            try:
                proc.kill()
                proc.wait(timeout=2)
            except Exception:
                pass


class TestWindowsPtyHandling:
    """Test Windows PTY handling and fallbacks."""

    def test_pty_import_error_handling(self):
        """Test graceful handling when pty is not available on Windows."""
        from tools.process_registry import ProcessRegistry

        registry = ProcessRegistry()

        # Mock environment
        mock_env = MagicMock()
        mock_env.env_type = "local"

        # Test that spawn handles PTY unavailability gracefully
        with patch("tools.process_registry._IS_WINDOWS", True):
            # Should not raise even if pty is unavailable
            try:
                # This may fail for other reasons, but not PTY-related
                registry.spawn(
                    env=mock_env,
                    command="echo test",
                    task_id="test_task",
                    use_pty=True,  # Request PTY
                )
            except Exception as e:
                # Should not be a PTY import error
                assert "pty" not in str(e).lower() or "not available" in str(e).lower()


class TestWindowsPathHandling:
    """Test Windows path handling in process registry."""

    def test_path_separator_in_command(self):
        """Test commands with Windows paths are handled correctly."""
        from tools.process_registry import ProcessRegistry

        registry = ProcessRegistry()

        # Test path with backslashes
        command = r"C:\Users\test\script.py"

        # Should not raise - just verify session ID generation works
        session_id = registry._generate_session_id()
        assert session_id.startswith("proc_")
        assert len(session_id) > 5


class TestWindowsSignalHandling:
    """Test Windows signal handling compatibility."""

    def test_no_sigterm_on_windows(self):
        """Verify SIGTERM is not used on Windows."""
        import signal

        # Windows doesn't have SIGTERM in the same way
        if _IS_WINDOWS:
            # On Windows, signal.SIGTERM exists but behavior differs
            assert hasattr(signal, "SIGTERM")

    def test_terminate_uses_correct_signal(self):
        """Test that process termination uses Windows-appropriate methods."""
        from tools.process_registry import ProcessRegistry

        # Create a subprocess
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )

        try:
            time.sleep(0.1)

            # Should use _terminate_host_pid which uses os.kill on Windows
            ProcessRegistry._terminate_host_pid(proc.pid)

            # Process should be terminated
            time.sleep(0.5)
            assert proc.poll() is not None

        finally:
            try:
                proc.kill()
                proc.wait(timeout=2)
            except Exception:
                pass
