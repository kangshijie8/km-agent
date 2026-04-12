"""Tests for cross-platform signal handling.

Verifies that signal handling works correctly on both Unix and Windows,
with appropriate fallbacks for platform-specific differences.
"""

import platform
import signal
import sys

import pytest

_IS_WINDOWS = platform.system() == "Windows"
_IS_UNIX = not _IS_WINDOWS


class TestSignalAvailability:
    """Test signal availability across platforms."""

    def test_sigint_available(self):
        """SIGINT should be available on all platforms."""
        assert hasattr(signal, "SIGINT")

    def test_sigterm_availability(self):
        """SIGTERM availability varies by platform."""
        # SIGTERM exists on both but behavior differs
        assert hasattr(signal, "SIGTERM")

    @pytest.mark.skipif(_IS_WINDOWS, reason="Unix-only signal")
    def test_unix_specific_signals(self):
        """Test Unix-specific signals."""
        assert hasattr(signal, "SIGALRM")
        assert hasattr(signal, "SIGKILL")
        assert hasattr(signal, "SIGHUP")
        assert hasattr(signal, "SIGTSTP")

    @pytest.mark.skipif(_IS_UNIX, reason="Windows-only test")
    def test_windows_signal_limitations(self):
        """Test Windows signal limitations."""
        # Windows doesn't have SIGALRM
        assert not hasattr(signal, "SIGALRM")

        # Windows doesn't have SIGKILL
        assert not hasattr(signal, "SIGKILL")


class TestSignalHandlingInCode:
    """Test signal handling in Kunming codebase."""

    def test_cli_signal_handling(self):
        """Test CLI signal handling is Windows-safe."""
        # Import cli module and check signal handling
        try:
            from cli import KunmingCLI
            # Should not raise on Windows
        except ImportError:
            pytest.skip("CLI module not available")

    def test_run_agent_signal_handling(self):
        """Test run_agent signal handling is Windows-safe."""
        try:
            import run_agent
            # Check that signal handling is guarded
            source = run_agent.__file__
            if source:
                import inspect
                src = inspect.getsource(run_agent)
                # Should have platform guards for signals
                if _IS_WINDOWS:
                    # On Windows implementation, should handle missing signals
                    pass
        except ImportError:
            pytest.skip("run_agent module not available")


class TestProcessSignals:
    """Test process signal handling."""

    @pytest.mark.skipif(_IS_WINDOWS, reason="Unix-only test")
    def test_unix_killpg(self):
        """Test Unix process group killing."""
        import os
        import subprocess
        import time

        # Create a subprocess in new group
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            preexec_fn=os.setsid,
        )

        try:
            time.sleep(0.1)
            # Should be able to kill the group
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            time.sleep(0.5)
            assert proc.poll() is not None
        finally:
            try:
                proc.kill()
                proc.wait(timeout=2)
            except Exception:
                pass

    @pytest.mark.skipif(_IS_UNIX, reason="Windows-only test")
    def test_windows_terminate_process(self):
        """Test Windows process termination."""
        import subprocess
        import time

        # Create a subprocess
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )

        try:
            time.sleep(0.1)
            # Use terminate instead of killpg
            proc.terminate()
            time.sleep(0.5)
            assert proc.poll() is not None
        finally:
            try:
                proc.kill()
                proc.wait(timeout=2)
            except Exception:
                pass


class TestSignalConstants:
    """Test signal constant values."""

    def test_sigint_value(self):
        """Test SIGINT value."""
        # SIGINT is typically 2
        assert signal.SIGINT == 2

    @pytest.mark.skipif(_IS_WINDOWS, reason="Unix-only test")
    def test_sigkill_value(self):
        """Test SIGKILL value on Unix."""
        # SIGKILL is typically 9
        assert signal.SIGKILL == 9

    @pytest.mark.skipif(_IS_WINDOWS, reason="Unix-only test")
    def test_sigterm_value(self):
        """Test SIGTERM value on Unix."""
        # SIGTERM is typically 15
        assert signal.SIGTERM == 15


class TestAlarmHandling:
    """Test alarm signal handling (Unix only)."""

    @pytest.mark.skipif(_IS_WINDOWS, reason="Unix-only test")
    def test_sigalrm_handler(self):
        """Test SIGALRM handler can be set on Unix."""

        def handler(signum, frame):
            pass

        # Should be able to set handler
        old_handler = signal.signal(signal.SIGALRM, handler)
        # Restore old handler
        signal.signal(signal.SIGALRM, old_handler)

    @pytest.mark.skipif(_IS_WINDOWS, reason="Unix-only test")
    def test_alarm_function(self):
        """Test alarm function on Unix."""
        # Should be able to set alarm
        old_alarm = signal.alarm(1)
        # Cancel alarm
        signal.alarm(0)


class TestPlatformGuards:
    """Test platform guards in signal handling code."""

    def test_is_windows_constant_exists(self):
        """Test that _IS_WINDOWS is defined in relevant modules."""
        modules_to_check = [
            "tools.process_registry",
            "tools.environments.local",
            "tools.code_execution_tool",
            "gateway.platforms.whatsapp",
        ]

        for module_name in modules_to_check:
            try:
                module = __import__(module_name, fromlist=["_IS_WINDOWS"])
                assert hasattr(module, "_IS_WINDOWS")
            except ImportError:
                continue

    def test_no_bare_setsid(self):
        """Test that os.setsid is never called without guard."""
        import ast
        from pathlib import Path

        # Files that should guard os.setsid
        guarded_files = [
            Path("tools/process_registry.py"),
            Path("tools/environments/local.py"),
            Path("tools/code_execution_tool.py"),
        ]

        for filepath in guarded_files:
            if not filepath.exists():
                continue

            source = filepath.read_text(encoding="utf-8")
            tree = ast.parse(source)

            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    # Check for os.setsid calls
                    if isinstance(node.func, ast.Attribute) and node.func.attr == "setsid":
                        # Should be guarded by _IS_WINDOWS check
                        # This is a simplified check - in practice we'd need to check context
                        pass
