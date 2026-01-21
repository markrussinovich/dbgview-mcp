"""
Unit tests for the CaptureManager and FilterSet classes.
"""

import re
import pytest
from unittest.mock import Mock, patch, MagicMock
import threading

from dbgcapture_mcp.capture_manager import (
    DebugEntry,
    FilterSet,
    Session,
    CaptureManager,
    get_manager,
)


class TestDebugEntry:
    """Tests for DebugEntry dataclass."""

    def test_create_entry(self):
        """Test creating a debug entry."""
        entry = DebugEntry(
            seq=1,
            time=132500000000000000,
            pid=1234,
            text="Test message"
        )
        assert entry.seq == 1
        assert entry.pid == 1234
        assert entry.text == "Test message"
        assert entry.process_name is None

    def test_create_entry_with_process_name(self):
        """Test creating a debug entry with process name."""
        entry = DebugEntry(
            seq=1,
            time=132500000000000000,
            pid=1234,
            text="Test message",
            process_name="python.exe"
        )
        assert entry.process_name == "python.exe"


class TestFilterSet:
    """Tests for FilterSet class."""

    def test_empty_filter_matches_everything(self):
        """Empty filter should match all entries."""
        filter_set = FilterSet()
        entry = DebugEntry(seq=1, time=0, pid=1234, text="Any message")
        assert filter_set.matches(entry) is True

    def test_include_pattern_match(self):
        """Include pattern should match entries with matching text."""
        filter_set = FilterSet(
            include_patterns=[re.compile(r"\[ERROR\]", re.IGNORECASE)]
        )
        
        matching = DebugEntry(seq=1, time=0, pid=1234, text="[ERROR] Something failed")
        non_matching = DebugEntry(seq=2, time=0, pid=1234, text="[INFO] All good")
        
        assert filter_set.matches(matching) is True
        assert filter_set.matches(non_matching) is False

    def test_multiple_include_patterns(self):
        """Multiple include patterns should match if any matches."""
        filter_set = FilterSet(
            include_patterns=[
                re.compile(r"\[ERROR\]", re.IGNORECASE),
                re.compile(r"\[WARN\]", re.IGNORECASE),
            ]
        )
        
        error_entry = DebugEntry(seq=1, time=0, pid=1234, text="[ERROR] Bad")
        warn_entry = DebugEntry(seq=2, time=0, pid=1234, text="[WARN] Caution")
        info_entry = DebugEntry(seq=3, time=0, pid=1234, text="[INFO] OK")
        
        assert filter_set.matches(error_entry) is True
        assert filter_set.matches(warn_entry) is True
        assert filter_set.matches(info_entry) is False

    def test_exclude_pattern_match(self):
        """Exclude pattern should reject matching entries."""
        filter_set = FilterSet(
            exclude_patterns=[re.compile(r"NOISE", re.IGNORECASE)]
        )
        
        matching = DebugEntry(seq=1, time=0, pid=1234, text="NOISE: Ignore this")
        non_matching = DebugEntry(seq=2, time=0, pid=1234, text="Important message")
        
        assert filter_set.matches(matching) is False
        assert filter_set.matches(non_matching) is True

    def test_exclude_takes_priority(self):
        """Exclude should take priority over include."""
        filter_set = FilterSet(
            include_patterns=[re.compile(r"\[ERROR\]", re.IGNORECASE)],
            exclude_patterns=[re.compile(r"SPAM", re.IGNORECASE)]
        )
        
        # Matches include but also matches exclude
        entry = DebugEntry(seq=1, time=0, pid=1234, text="[ERROR] SPAM message")
        assert filter_set.matches(entry) is False

    def test_process_pid_filter(self):
        """Process PID filter should limit to specified PIDs."""
        filter_set = FilterSet(process_pids=[1234, 5678])
        
        matching = DebugEntry(seq=1, time=0, pid=1234, text="From allowed PID")
        non_matching = DebugEntry(seq=2, time=0, pid=9999, text="From other PID")
        
        assert filter_set.matches(matching) is True
        assert filter_set.matches(non_matching) is False

    def test_process_name_filter(self):
        """Process name filter should match by regex."""
        filter_set = FilterSet(
            process_names=[re.compile(r"python", re.IGNORECASE)]
        )
        
        matching = DebugEntry(seq=1, time=0, pid=1234, text="Message", process_name="python.exe")
        non_matching = DebugEntry(seq=2, time=0, pid=5678, text="Message", process_name="notepad.exe")
        no_name = DebugEntry(seq=3, time=0, pid=9999, text="Message", process_name=None)
        
        assert filter_set.matches(matching) is True
        assert filter_set.matches(non_matching) is False
        assert filter_set.matches(no_name) is False

    def test_combined_filters(self):
        """Test combination of all filter types."""
        filter_set = FilterSet(
            include_patterns=[re.compile(r"\[DEBUG\]")],
            exclude_patterns=[re.compile(r"VERBOSE")],
            process_pids=[1234],
        )
        
        # Must match: correct PID, has [DEBUG], no VERBOSE
        good = DebugEntry(seq=1, time=0, pid=1234, text="[DEBUG] Important")
        assert filter_set.matches(good) is True
        
        # Wrong PID
        wrong_pid = DebugEntry(seq=2, time=0, pid=9999, text="[DEBUG] Important")
        assert filter_set.matches(wrong_pid) is False
        
        # No [DEBUG]
        no_debug = DebugEntry(seq=3, time=0, pid=1234, text="[INFO] Something")
        assert filter_set.matches(no_debug) is False
        
        # Has VERBOSE (excluded)
        verbose = DebugEntry(seq=4, time=0, pid=1234, text="[DEBUG] VERBOSE stuff")
        assert filter_set.matches(verbose) is False


class TestSession:
    """Tests for Session dataclass."""

    def test_create_session(self):
        """Test creating a session."""
        session = Session(
            id="abc123",
            name="test-session",
            filters=FilterSet(),
            cursor=0,
            created_at=1000.0
        )
        assert session.id == "abc123"
        assert session.name == "test-session"
        assert session.cursor == 0


class TestCaptureManager:
    """Tests for CaptureManager class."""

    @pytest.fixture
    def mock_manager(self):
        """Create a manager with mocked subprocess."""
        # Reset singleton for testing
        CaptureManager._instance = None
        
        with patch('dbgcapture_mcp.capture_manager.subprocess') as mock_subprocess:
            mock_process = MagicMock()
            mock_process.poll.return_value = None  # Process is running
            mock_process.stdout.readline.return_value = ""
            mock_subprocess.Popen.return_value = mock_process
            mock_subprocess.CREATE_NO_WINDOW = 0
            
            manager = CaptureManager()
            manager._capture_exe = MagicMock()
            manager._capture_exe.exists.return_value = True
            manager._capture_exe.__str__ = lambda x: "dbgcapture.exe"
            
            yield manager
            
            # Cleanup
            manager._running = False
            CaptureManager._instance = None

    def test_singleton_pattern(self):
        """Manager should be a singleton."""
        CaptureManager._instance = None
        try:
            m1 = CaptureManager()
            m2 = CaptureManager()
            assert m1 is m2
        finally:
            CaptureManager._instance = None

    def test_create_session(self, mock_manager):
        """Test session creation."""
        session_id = mock_manager.create_session("test")
        assert session_id is not None
        assert len(session_id) == 8
        
        session = mock_manager.get_session(session_id)
        assert session is not None
        assert session.name == "test"

    def test_create_session_default_name(self, mock_manager):
        """Session should get default name if none provided."""
        session_id = mock_manager.create_session()
        session = mock_manager.get_session(session_id)
        assert session.name.startswith("session-")

    def test_destroy_session(self, mock_manager):
        """Test session destruction."""
        session_id = mock_manager.create_session("test")
        assert mock_manager.get_session(session_id) is not None
        
        result = mock_manager.destroy_session(session_id)
        assert result is True
        assert mock_manager.get_session(session_id) is None

    def test_destroy_nonexistent_session(self, mock_manager):
        """Destroying nonexistent session should return False."""
        result = mock_manager.destroy_session("nonexistent")
        assert result is False

    def test_set_filters(self, mock_manager):
        """Test setting filters on a session."""
        session_id = mock_manager.create_session("test")
        
        result = mock_manager.set_filters(
            session_id,
            include=[r"\[ERROR\]"],
            exclude=[r"NOISE"],
            process_pids=[1234]
        )
        assert result is True
        
        session = mock_manager.get_session(session_id)
        assert len(session.filters.include_patterns) == 1
        assert len(session.filters.exclude_patterns) == 1
        assert session.filters.process_pids == [1234]

    def test_set_filters_invalid_session(self, mock_manager):
        """Setting filters on invalid session should fail."""
        result = mock_manager.set_filters("nonexistent", include=[r"test"])
        assert result is False

    def test_get_output_empty(self, mock_manager):
        """Get output from empty buffer."""
        session_id = mock_manager.create_session("test")
        entries, next_seq = mock_manager.get_output(session_id)
        assert entries == []
        assert next_seq == 0

    def test_get_output_with_entries(self, mock_manager):
        """Get output with buffered entries."""
        session_id = mock_manager.create_session("test")
        
        # Add entries directly to buffer
        mock_manager._buffer.append(DebugEntry(
            seq=1, time=0, pid=1234, text="Message 1", process_name="test.exe"
        ))
        mock_manager._buffer.append(DebugEntry(
            seq=2, time=0, pid=1234, text="Message 2", process_name="test.exe"
        ))
        
        entries, next_seq = mock_manager.get_output(session_id, limit=10)
        assert len(entries) == 2
        assert entries[0]["text"] == "Message 1"
        assert entries[1]["text"] == "Message 2"

    def test_get_output_with_filter(self, mock_manager):
        """Get output should respect filters."""
        session_id = mock_manager.create_session("test")
        mock_manager.set_filters(session_id, include=[r"IMPORTANT"])
        
        mock_manager._buffer.append(DebugEntry(
            seq=1, time=0, pid=1234, text="IMPORTANT: Look at this"
        ))
        mock_manager._buffer.append(DebugEntry(
            seq=2, time=0, pid=1234, text="noise: ignore this"
        ))
        mock_manager._buffer.append(DebugEntry(
            seq=3, time=0, pid=1234, text="IMPORTANT: Another one"
        ))
        
        entries, _ = mock_manager.get_output(session_id, limit=10)
        assert len(entries) == 2
        assert all("IMPORTANT" in e["text"] for e in entries)

    def test_get_output_respects_limit(self, mock_manager):
        """Get output should respect limit parameter."""
        session_id = mock_manager.create_session("test")
        
        for i in range(10):
            mock_manager._buffer.append(DebugEntry(
                seq=i+1, time=0, pid=1234, text=f"Message {i+1}"
            ))
        
        entries, _ = mock_manager.get_output(session_id, limit=3)
        assert len(entries) == 3

    def test_clear_session(self, mock_manager):
        """Clear session should skip pending entries."""
        session_id = mock_manager.create_session("test")
        
        # Add entries
        for i in range(5):
            mock_manager._buffer.append(DebugEntry(
                seq=i+1, time=0, pid=1234, text=f"Message {i+1}"
            ))
        mock_manager._current_seq = 5
        
        # Clear should move cursor to current
        result = mock_manager.clear_session(session_id)
        assert result is True
        
        session = mock_manager.get_session(session_id)
        assert session.cursor == 5
        
        # No pending entries
        entries, _ = mock_manager.get_output(session_id)
        assert len(entries) == 0

    def test_get_session_status(self, mock_manager):
        """Get session status should return correct info."""
        session_id = mock_manager.create_session("test")
        mock_manager.set_filters(session_id, include=[r"ERROR"])
        
        status = mock_manager.get_session_status(session_id)
        assert status is not None
        assert status["session_id"] == session_id
        assert status["name"] == "test"
        assert "filters" in status
        assert "ERROR" in status["filters"]["include"]

    def test_list_processes(self, mock_manager):
        """Test process listing."""
        with patch('dbgcapture_mcp.capture_manager.psutil') as mock_psutil:
            mock_proc1 = MagicMock()
            mock_proc1.info = {"pid": 1234, "name": "python.exe"}
            mock_proc2 = MagicMock()
            mock_proc2.info = {"pid": 5678, "name": "notepad.exe"}
            
            mock_psutil.process_iter.return_value = [mock_proc1, mock_proc2]
            
            processes = mock_manager.list_processes()
            assert len(processes) == 2

    def test_list_processes_with_filter(self, mock_manager):
        """Test process listing with name filter."""
        with patch('dbgcapture_mcp.capture_manager.psutil') as mock_psutil:
            mock_proc1 = MagicMock()
            mock_proc1.info = {"pid": 1234, "name": "python.exe"}
            mock_proc2 = MagicMock()
            mock_proc2.info = {"pid": 5678, "name": "notepad.exe"}
            
            mock_psutil.process_iter.return_value = [mock_proc1, mock_proc2]
            
            processes = mock_manager.list_processes("python")
            assert len(processes) == 1
            assert processes[0]["name"] == "python.exe"


class TestGetManager:
    """Tests for get_manager function."""

    def test_get_manager_returns_singleton(self):
        """get_manager should return the same instance."""
        import dbgcapture_mcp.capture_manager as cm
        cm._manager = None
        CaptureManager._instance = None
        
        try:
            m1 = get_manager()
            m2 = get_manager()
            assert m1 is m2
        finally:
            cm._manager = None
            CaptureManager._instance = None
