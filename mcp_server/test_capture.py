"""
Test script for the debug capture MCP server.

Sends OutputDebugString messages and verifies capture works.
"""

import ctypes
import sys
import time
import os

# Add parent to path for importing
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dbgcapture_mcp.capture_manager import get_manager


def send_debug_string(message: str):
    """Send a debug string via OutputDebugString."""
    ctypes.windll.kernel32.OutputDebugStringA(message.encode('ascii') + b'\0')


def test_capture():
    """Test the capture manager."""
    print("=== Debug Capture Test ===\n")
    
    manager = get_manager()
    
    # Create a session
    print("1. Creating session...")
    session_id = manager.create_session("test-session")
    print(f"   Session ID: {session_id}")
    
    # Check status
    status = manager.get_session_status(session_id)
    print(f"   Capture running: {status['capture_running']}")
    
    # Wait for capture to start
    time.sleep(0.5)
    
    # Send some test messages
    print("\n2. Sending test debug messages...")
    test_messages = [
        "[TEST] Hello from debug capture test!",
        "[TEST] Message 2 - testing capture",
        "[TEST] Message 3 - with special chars: <>&\"'",
        "[INFO] This is an info message",
        "[ERROR] This is an error message",
        "[DEBUG] This should be filtered out later",
    ]
    
    for msg in test_messages:
        send_debug_string(msg)
        print(f"   Sent: {msg}")
        time.sleep(0.1)  # Small delay between messages
    
    # Wait for messages to be captured
    time.sleep(0.5)
    
    # Get output
    print("\n3. Getting captured output...")
    entries, next_seq = manager.get_output(session_id, limit=20)
    print(f"   Captured {len(entries)} entries")
    
    for entry in entries:
        print(f"   [{entry['seq']}] PID={entry['pid']} ({entry['process_name']}): {entry['text'][:60]}...")
    
    # Test filtering
    print("\n4. Testing filters - include only [TEST] messages...")
    manager.set_filters(session_id, include=[r"\[TEST\]"])
    
    # Send more messages
    send_debug_string("[TEST] This should appear")
    send_debug_string("[INFO] This should NOT appear")
    send_debug_string("[TEST] This should also appear")
    time.sleep(0.3)
    
    entries, next_seq = manager.get_output(session_id, limit=20)
    print(f"   Got {len(entries)} filtered entries:")
    for entry in entries:
        print(f"   - {entry['text']}")
    
    # Test exclude filter
    print("\n5. Testing exclude filter - exclude [ERROR] messages...")
    manager.set_filters(session_id, exclude=[r"\[ERROR\]"])
    
    send_debug_string("[INFO] Info should appear")
    send_debug_string("[ERROR] Error should NOT appear")
    send_debug_string("[DEBUG] Debug should appear")
    time.sleep(0.3)
    
    entries, next_seq = manager.get_output(session_id, limit=20)
    print(f"   Got {len(entries)} entries (ERROR excluded):")
    for entry in entries:
        print(f"   - {entry['text']}")
    
    # Test process filter
    print("\n6. Listing processes matching 'python'...")
    processes = manager.list_processes("python")
    print(f"   Found {len(processes)} matching processes:")
    for proc in processes[:5]:
        print(f"   - PID {proc['pid']}: {proc['name']}")
    
    # Clean up
    print("\n7. Cleaning up...")
    manager.destroy_session(session_id)
    print("   Session destroyed")
    print(f"   Capture still running: {manager.is_running()}")
    
    print("\n=== Test Complete ===")


if __name__ == "__main__":
    test_capture()
