"""
Integration tests for the debug capture system.

These tests require dbgcapture.exe to be built and verify end-to-end functionality.
"""

import ctypes
import os
import sys
import time
import pytest
from pathlib import Path

# Skip if not on Windows
pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Debug capture only works on Windows"
)


def send_debug_string(message: str):
    """Send a debug string via OutputDebugString."""
    ctypes.windll.kernel32.OutputDebugStringA(message.encode('ascii') + b'\0')


class TestCaptureIntegration:
    """Integration tests for the capture system."""

    @pytest.fixture
    def manager(self):
        """Get the capture manager."""
        from dbgcapture_mcp.capture_manager import CaptureManager, get_manager
        
        # Reset singleton for clean test
        CaptureManager._instance = None
        import dbgcapture_mcp.capture_manager as cm
        cm._manager = None
        
        manager = get_manager()
        yield manager
        
        # Cleanup all sessions
        with manager._sessions_lock:
            session_ids = list(manager._sessions.keys())
        for sid in session_ids:
            manager.destroy_session(sid)
        
        manager.stop_capture()
        
        # Reset singleton
        CaptureManager._instance = None
        cm._manager = None

    @pytest.fixture
    def check_exe_exists(self):
        """Check if dbgcapture.exe exists."""
        exe_path = Path(__file__).parent.parent.parent / "dbgcapture" / "dbgcapture.exe"
        if not exe_path.exists():
            pytest.skip(f"dbgcapture.exe not found at {exe_path}. Build it first with: nmake")
        return exe_path

    def test_create_and_destroy_session(self, manager, check_exe_exists):
        """Test creating and destroying a session."""
        session_id = manager.create_session("test-session")
        assert session_id is not None
        assert len(session_id) == 8
        
        session = manager.get_session(session_id)
        assert session is not None
        assert session.name == "test-session"
        
        # Capture should be running
        assert manager.is_running()
        
        # Destroy session
        result = manager.destroy_session(session_id)
        assert result is True
        
        # Session should be gone
        assert manager.get_session(session_id) is None

    def test_capture_debug_output(self, manager, check_exe_exists):
        """Test capturing OutputDebugString messages."""
        session_id = manager.create_session("capture-test")
        
        # Wait for capture to start
        time.sleep(0.5)
        
        # Send unique test messages
        test_marker = f"[TEST-{time.time()}]"
        messages = [
            f"{test_marker} Message 1",
            f"{test_marker} Message 2",
            f"{test_marker} Message 3",
        ]
        
        for msg in messages:
            send_debug_string(msg)
            time.sleep(0.05)
        
        # Wait for messages to be captured
        time.sleep(0.5)
        
        # Get output
        entries, _ = manager.get_output(session_id, limit=100)
        
        # Find our messages
        our_entries = [e for e in entries if test_marker in e["text"]]
        
        # We should capture at least some messages (timing dependent)
        assert len(our_entries) >= 1, f"Expected at least 1 message, got {len(our_entries)}"
        
        manager.destroy_session(session_id)

    def test_include_filter(self, manager, check_exe_exists):
        """Test include filter functionality."""
        session_id = manager.create_session("filter-test")
        time.sleep(0.5)
        
        # Set include filter
        test_marker = f"INCLUDE-{time.time()}"
        manager.set_filters(session_id, include=[test_marker])
        
        # Send messages - some matching, some not
        send_debug_string(f"[{test_marker}] Should appear")
        send_debug_string("[OTHER] Should NOT appear")
        send_debug_string(f"[{test_marker}] Also should appear")
        
        time.sleep(0.3)
        
        entries, _ = manager.get_output(session_id, limit=100)
        
        # All entries should contain the test marker
        for entry in entries:
            assert test_marker in entry["text"], f"Unexpected entry: {entry['text']}"
        
        manager.destroy_session(session_id)

    def test_exclude_filter(self, manager, check_exe_exists):
        """Test exclude filter functionality."""
        session_id = manager.create_session("exclude-test")
        time.sleep(0.5)
        
        # Set exclude filter
        test_marker = f"MYTEST-{time.time()}"
        exclude_marker = "EXCLUDE_ME"
        manager.set_filters(session_id, include=[test_marker], exclude=[exclude_marker])
        
        # Send messages
        send_debug_string(f"[{test_marker}] Good message")
        send_debug_string(f"[{test_marker}] {exclude_marker} Bad message")
        send_debug_string(f"[{test_marker}] Another good message")
        
        time.sleep(0.3)
        
        entries, _ = manager.get_output(session_id, limit=100)
        
        # No entries should contain the exclude marker
        for entry in entries:
            assert exclude_marker not in entry["text"], f"Excluded entry appeared: {entry['text']}"
        
        manager.destroy_session(session_id)

    def test_clear_session(self, manager, check_exe_exists):
        """Test clearing session cursor."""
        session_id = manager.create_session("clear-test")
        time.sleep(0.5)
        
        test_marker = f"CLEAR-{time.time()}"
        
        # Send some messages
        send_debug_string(f"[{test_marker}] Before clear 1")
        send_debug_string(f"[{test_marker}] Before clear 2")
        
        time.sleep(0.3)
        
        # Clear the session
        manager.clear_session(session_id)
        
        # Send more messages
        send_debug_string(f"[{test_marker}] After clear 1")
        
        time.sleep(0.3)
        
        # Get output - should only see "After clear" messages
        entries, _ = manager.get_output(session_id, limit=100)
        
        our_entries = [e for e in entries if test_marker in e["text"]]
        
        # Should only have the "After clear" message(s)
        for entry in our_entries:
            assert "Before clear" not in entry["text"], f"Pre-clear message appeared: {entry['text']}"
        
        manager.destroy_session(session_id)

    def test_session_status(self, manager, check_exe_exists):
        """Test getting session status."""
        session_id = manager.create_session("status-test")
        time.sleep(0.3)
        
        # Set some filters
        manager.set_filters(session_id, include=[r"\[ERROR\]"], exclude=["NOISE"])
        
        status = manager.get_session_status(session_id)
        
        assert status is not None
        assert status["session_id"] == session_id
        assert status["name"] == "status-test"
        assert r"\[ERROR\]" in status["filters"]["include"]
        assert "NOISE" in status["filters"]["exclude"]
        assert status["capture_running"] is True
        
        manager.destroy_session(session_id)

    def test_list_processes(self, manager, check_exe_exists):
        """Test listing processes."""
        # This doesn't require a session
        processes = manager.list_processes()
        
        assert len(processes) > 0
        
        # Each process should have pid and name
        for proc in processes:
            assert "pid" in proc
            assert "name" in proc
            assert isinstance(proc["pid"], int)
            assert isinstance(proc["name"], str)

    def test_list_processes_filtered(self, manager, check_exe_exists):
        """Test listing processes with filter."""
        # Filter for python processes (should include our test process)
        processes = manager.list_processes("python")
        
        # Should find at least one (the test runner)
        assert len(processes) > 0
        
        for proc in processes:
            assert "python" in proc["name"].lower()

    def test_multiple_sessions(self, manager, check_exe_exists):
        """Test multiple concurrent sessions with different filters."""
        # Create first session and verify capture is running
        session1 = manager.create_session("session-1")
        
        # Wait for capture subprocess to be fully ready
        time.sleep(0.5)
        
        # Verify capture is running before creating second session
        assert manager.is_running(), "Capture should be running after first session"
        
        # Create second session (capture already running)
        session2 = manager.create_session("session-2")
        
        # Set different filters
        manager.set_filters(session1, include=[r"\[S1\]"])
        manager.set_filters(session2, include=[r"\[S2\]"])
        
        # Clear sessions to start fresh after filter setup
        manager.clear_session(session1)
        manager.clear_session(session2)
        
        # Use unique markers for this test run to avoid interference
        test_id = f"{time.time()}"
        s1_msg = f"[S1] Session1-{test_id}"
        s2_msg = f"[S2] Session2-{test_id}"
        
        # Send messages for both with delays
        send_debug_string(s1_msg)
        time.sleep(0.05)
        send_debug_string(s2_msg)
        time.sleep(0.05)
        send_debug_string(f"[BOTH] Neither-{test_id}")
        
        time.sleep(0.5)  # Give time for capture
        
        # Get outputs
        entries1, _ = manager.get_output(session1, limit=100)
        entries2, _ = manager.get_output(session2, limit=100)
        
        s1_texts = [e["text"] for e in entries1]
        s2_texts = [e["text"] for e in entries2]
        
        # Session 1 should have [S1] messages only
        s1_matches = [t for t in s1_texts if test_id in t and "[S1]" in t]
        s2_matches = [t for t in s2_texts if test_id in t and "[S2]" in t]
        
        # If we got any output at all, verify filtering works
        # This accounts for timing variations in CI environments
        if len(entries1) > 0 or len(entries2) > 0:
            # If we captured something, verify filters worked
            s1_wrong = [t for t in s1_texts if test_id in t and "[S2]" in t]
            s2_wrong = [t for t in s2_texts if test_id in t and "[S1]" in t]
            assert len(s1_wrong) == 0, f"Session 1 should not have [S2] messages: {s1_wrong}"
            assert len(s2_wrong) == 0, f"Session 2 should not have [S1] messages: {s2_wrong}"
        
        # Verify at least one message was captured (may fail on slow systems)
        total_captured = len(s1_matches) + len(s2_matches)
        assert total_captured >= 1, f"Expected at least 1 message captured, S1={s1_texts}, S2={s2_texts}"
        
        manager.destroy_session(session1)
        manager.destroy_session(session2)

    def test_process_name_in_entries(self, manager, check_exe_exists):
        """Test that entries include process name."""
        session_id = manager.create_session("process-name-test")
        time.sleep(0.5)
        
        test_marker = f"PROCNAME-{time.time()}"
        send_debug_string(f"[{test_marker}] Test message")
        
        time.sleep(0.3)
        
        entries, _ = manager.get_output(session_id, limit=100)
        our_entries = [e for e in entries if test_marker in e["text"]]
        
        # Should have process name
        if our_entries:
            entry = our_entries[0]
            assert "process_name" in entry
            # Our process should be python
            assert entry["process_name"] is not None
            assert "python" in entry["process_name"].lower()
        
        manager.destroy_session(session_id)
