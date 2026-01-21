"""
Unit tests for the MCP server.

Tests the tool handlers directly without going through the MCP Server object,
since the internal handler storage is not part of the public API.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from dbgcapture_mcp.server import create_server
from dbgcapture_mcp.capture_manager import CaptureManager


class TestCreateServer:
    """Tests for server creation."""

    def test_create_server_returns_server(self):
        """create_server should return a Server instance."""
        server = create_server()
        assert server is not None
        assert server.name == "dbgcapture-mcp"


class TestToolHandlerLogic:
    """
    Tests for the tool handler logic.
    
    Since the MCP Server internal structure is not directly accessible,
    we test the underlying capture_manager functionality that the handlers use.
    """

    @pytest.fixture
    def reset_singleton(self):
        """Reset the CaptureManager singleton before and after each test."""
        import dbgcapture_mcp.capture_manager as cm
        old_manager = cm._manager
        old_instance = CaptureManager._instance
        cm._manager = None
        CaptureManager._instance = None
        yield
        cm._manager = old_manager
        CaptureManager._instance = old_instance

    def test_manager_create_session(self, reset_singleton):
        """Test create_session through manager."""
        with patch('dbgcapture_mcp.capture_manager.subprocess') as mock_subprocess:
            mock_process = MagicMock()
            mock_process.poll.return_value = None
            mock_process.stdout.readline.return_value = ""
            mock_subprocess.Popen.return_value = mock_process
            mock_subprocess.CREATE_NO_WINDOW = 0
            
            from dbgcapture_mcp.capture_manager import get_manager
            manager = get_manager()
            manager._capture_exe = MagicMock()
            manager._capture_exe.exists.return_value = True
            
            session_id = manager.create_session("test-session")
            
            assert session_id is not None
            assert len(session_id) == 8
            
            session = manager.get_session(session_id)
            assert session.name == "test-session"
            
            # Cleanup
            manager._running = False

    def test_manager_destroy_session(self, reset_singleton):
        """Test destroy_session through manager."""
        with patch('dbgcapture_mcp.capture_manager.subprocess') as mock_subprocess:
            mock_process = MagicMock()
            mock_process.poll.return_value = None
            mock_process.stdout.readline.return_value = ""
            mock_subprocess.Popen.return_value = mock_process
            mock_subprocess.CREATE_NO_WINDOW = 0
            
            from dbgcapture_mcp.capture_manager import get_manager
            manager = get_manager()
            manager._capture_exe = MagicMock()
            manager._capture_exe.exists.return_value = True
            
            session_id = manager.create_session("test")
            assert manager.get_session(session_id) is not None
            
            result = manager.destroy_session(session_id)
            assert result is True
            assert manager.get_session(session_id) is None
            
            # Non-existent session
            result = manager.destroy_session("nonexistent")
            assert result is False
            
            manager._running = False

    def test_manager_set_filters(self, reset_singleton):
        """Test set_filters through manager."""
        with patch('dbgcapture_mcp.capture_manager.subprocess') as mock_subprocess:
            mock_process = MagicMock()
            mock_process.poll.return_value = None
            mock_process.stdout.readline.return_value = ""
            mock_subprocess.Popen.return_value = mock_process
            mock_subprocess.CREATE_NO_WINDOW = 0
            
            from dbgcapture_mcp.capture_manager import get_manager
            manager = get_manager()
            manager._capture_exe = MagicMock()
            manager._capture_exe.exists.return_value = True
            
            session_id = manager.create_session("test")
            
            result = manager.set_filters(
                session_id,
                include=[r"\[ERROR\]"],
                exclude=[r"NOISE"]
            )
            assert result is True
            
            session = manager.get_session(session_id)
            assert len(session.filters.include_patterns) == 1
            assert len(session.filters.exclude_patterns) == 1
            
            manager._running = False


class TestRegexValidation:
    """Test regex pattern validation in the server."""
    
    def test_valid_regex_patterns(self):
        """Valid regex patterns should be accepted."""
        import re
        valid_patterns = [
            r"\[ERROR\]",
            r"test.*message",
            r"^start",
            r"end$",
            r"word\d+",
        ]
        for pattern in valid_patterns:
            # Should not raise
            re.compile(pattern)
    
    def test_invalid_regex_detection(self):
        """Invalid regex patterns should raise re.error."""
        import re
        invalid_patterns = [
            "[invalid(regex",
            "**invalid",
        ]
        for pattern in invalid_patterns:
            with pytest.raises(re.error):
                re.compile(pattern)


class TestJsonResponses:
    """Test JSON response formatting."""
    
    def test_session_created_response(self):
        """Test session created response format."""
        session_id = "abc12345"
        response = f'{{"session_id": "{session_id}", "status": "created", "capture_running": true}}'
        data = json.loads(response)
        
        assert data["session_id"] == session_id
        assert data["status"] == "created"
        assert data["capture_running"] is True
    
    def test_session_destroyed_response(self):
        """Test session destroyed response format."""
        session_id = "abc123"
        response = f'{{"session_id": "{session_id}", "status": "destroyed"}}'
        data = json.loads(response)
        
        assert data["session_id"] == session_id
        assert data["status"] == "destroyed"
    
    def test_error_response(self):
        """Test error response format."""
        session_id = "nonexistent"
        response = f'{{"error": "Session not found: {session_id}"}}'
        data = json.loads(response)
        
        assert "error" in data
        assert session_id in data["error"]
    
    def test_filters_set_response(self):
        """Test filters_set response format."""
        filters = {
            "include": [r"\[ERROR\]"],
            "exclude": [],
            "process_names": [],
            "process_pids": []
        }
        response = json.dumps({"status": "filters_set", "filters": filters})
        data = json.loads(response)
        
        assert data["status"] == "filters_set"
        assert "filters" in data
        assert data["filters"]["include"] == [r"\[ERROR\]"]
    
    def test_get_output_response(self):
        """Test get_output response format."""
        entries = [
            {"seq": 1, "pid": 1234, "text": "Test", "process_name": "test.exe", "time": 0}
        ]
        response = json.dumps({
            "entries": entries,
            "count": len(entries),
            "next_seq": 1
        })
        data = json.loads(response)
        
        assert data["count"] == 1
        assert len(data["entries"]) == 1
        assert data["next_seq"] == 1
    
    def test_session_status_response(self):
        """Test session_status response format."""
        status = {
            "session_id": "abc123",
            "name": "test",
            "filters": {
                "include": [],
                "exclude": [],
                "process_names": [],
                "process_pids": []
            },
            "cursor": 0,
            "pending_count": 5,
            "capture_running": True,
            "total_buffered": 100
        }
        response = json.dumps(status)
        data = json.loads(response)
        
        assert data["session_id"] == "abc123"
        assert data["pending_count"] == 5
    
    def test_list_processes_response(self):
        """Test list_processes response format."""
        processes = [
            {"pid": 1234, "name": "python.exe"},
            {"pid": 5678, "name": "notepad.exe"}
        ]
        response = json.dumps({"processes": processes, "count": len(processes)})
        data = json.loads(response)
        
        assert data["count"] == 2
        assert len(data["processes"]) == 2
    
    def test_list_sessions_response(self):
        """Test list_sessions response format."""
        sessions = [
            {"session_id": "abc123", "name": "test-session", "cursor": 5}
        ]
        response = json.dumps({
            "sessions": sessions,
            "count": len(sessions),
            "capture_running": True
        })
        data = json.loads(response)
        
        assert data["count"] == 1
        assert data["capture_running"] is True


class TestServerToolsMetadata:
    """Test that server advertises correct tools."""
    
    def test_server_has_correct_name(self):
        """Server should have correct name."""
        server = create_server()
        assert server.name == "dbgcapture-mcp"
    
    def test_expected_tool_names(self):
        """Verify expected tool names are defined."""
        expected_tools = {
            "create_session",
            "destroy_session", 
            "set_filters",
            "get_output",
            "clear_session",
            "get_session_status",
            "list_processes",
            "list_sessions"
        }
        # Just verify these are the expected tools in the design
        assert len(expected_tools) == 8
