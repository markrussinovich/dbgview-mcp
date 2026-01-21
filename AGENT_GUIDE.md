# Debug Capture MCP Server - Agent Guide

This guide explains how to use the `dbgcapture` MCP server to monitor Windows debug output from applications.

## Overview

The `dbgcapture` MCP server captures `OutputDebugString` messages from Windows applications. This is useful for:
- Monitoring application debug output in real-time
- Filtering logs by pattern or process
- Debugging applications without a debugger attached

## Available MCP Tools

### Session Management

| Tool | Description |
|------|-------------|
| `create_session` | Create a capture session. Returns a `session_id`. |
| `destroy_session` | End a session and free resources. |
| `list_sessions` | List all active sessions. |
| `get_session_status` | Get session info: filters, pending count, capture state. |

### Capture & Filtering

| Tool | Description |
|------|-------------|
| `get_output` | Get captured debug messages (respects filters). |
| `set_filters` | Set include/exclude regex patterns and process filters. |
| `clear_session` | Skip pending messages, start fresh from now. |

### Process Discovery

| Tool | Description |
|------|-------------|
| `list_processes` | List running processes (optionally filtered by name). |

## Quick Start

### 1. Create a Session

```json
// Tool: create_session
{"name": "my-monitor"}

// Response:
{"session_id": "abc12345", "status": "created", "capture_running": true}
```

### 2. Get Debug Output

```json
// Tool: get_output
{"session_id": "abc12345", "limit": 50}

// Response:
{
  "entries": [
    {"seq": 1, "pid": 1234, "process_name": "myapp.exe", "text": "[INFO] Started", "time": 133...},
    {"seq": 2, "pid": 1234, "process_name": "myapp.exe", "text": "[ERROR] Failed", "time": 133...}
  ],
  "count": 2,
  "next_seq": 2
}
```

### 3. Set Filters (Optional)

```json
// Tool: set_filters
{
  "session_id": "abc12345",
  "include": ["\\[ERROR\\]", "\\[WARN\\]"],
  "exclude": ["\\[VERBOSE\\]"]
}

// Now get_output only returns ERROR and WARN messages (excluding VERBOSE)
```

### 4. Cleanup

```json
// Tool: destroy_session
{"session_id": "abc12345"}
```

## Filter Examples

### Include Only Errors
```json
{"session_id": "...", "include": ["\\[ERROR\\]"]}
```

### Include Errors and Warnings
```json
{"session_id": "...", "include": ["\\[ERROR\\]", "\\[WARN\\]"]}
```

### Exclude Noise
```json
{"session_id": "...", "exclude": ["\\[TRACE\\]", "\\[VERBOSE\\]", "HEARTBEAT"]}
```

### Filter by Process Name
```json
{"session_id": "...", "process_names": ["myapp", "python"]}
```

### Filter by Process ID
```json
{"session_id": "...", "process_pids": [1234, 5678]}
```

### Combined Filters
```json
{
  "session_id": "...",
  "include": ["\\[ERROR\\]"],
  "exclude": ["expected error"],
  "process_names": ["myapp"]
}
```

## Polling for New Messages

Use `next_seq` from the response to get only new messages:

```json
// First call
{"session_id": "abc12345", "limit": 100}
// Response: {"entries": [...], "next_seq": 42}

// Subsequent calls - only get messages after seq 42
{"session_id": "abc12345", "limit": 100, "since_seq": 42}
```

## Test Application

A test application is provided to generate debug output for testing:

**Location:** `MCP/test_debug_app.py`

### Test App Commands

```bash
# Basic - 10 messages with [TEST] tag
python test_debug_app.py

# Custom tag and count
python test_debug_app.py --tag MYAPP --count 50 --interval 0.2

# Multiple random tags (INFO, DEBUG, WARN, ERROR, TRACE, VERBOSE)
python test_debug_app.py --multi-tag --count 100

# Diverse patterns for regex testing
python test_debug_app.py --pattern --count 3

# Continuous mode (Ctrl+C to stop)
python test_debug_app.py --continuous --interval 1.0

# High-throughput burst
python test_debug_app.py --burst 5000

# Interactive - type messages manually
python test_debug_app.py --interactive
```

### Test App Modes

| Mode | Flag | Purpose |
|------|------|---------|
| Basic | (default) | Simple message stream with one tag |
| Multi-tag | `--multi-tag` | Random tags for filter testing |
| Pattern | `--pattern` | Diverse patterns (HTTP, DB, errors, etc.) |
| Continuous | `--continuous` | Real-time monitoring test |
| Burst | `--burst N` | High-throughput stress test |
| Interactive | `--interactive` | Manual message entry |

## Complete Workflow Example

Here's a complete example of monitoring an application:

### Step 1: Start Capture
```
Tool: create_session
Args: {"name": "app-monitor"}
→ session_id: "abc12345"
```

### Step 2: Start the Test App (in a terminal)
```bash
python MCP/test_debug_app.py --pattern --count 5 -v
```

### Step 3: Get All Output
```
Tool: get_output
Args: {"session_id": "abc12345", "limit": 100}
→ Returns all captured messages
```

### Step 4: Set Filter for Errors Only
```
Tool: set_filters
Args: {"session_id": "abc12345", "include": ["\\[ERROR\\]", "\\[WARN\\]"]}
```

### Step 5: Clear and Re-run
```
Tool: clear_session
Args: {"session_id": "abc12345"}
```

Run the test app again, then:
```
Tool: get_output
Args: {"session_id": "abc12345", "limit": 100}
→ Only ERROR and WARN messages
```

### Step 6: Check Status
```
Tool: get_session_status
Args: {"session_id": "abc12345"}
→ Shows filters, pending count, capture state
```

### Step 7: Find Process
```
Tool: list_processes
Args: {"name_pattern": "python"}
→ Lists Python processes with PIDs
```

### Step 8: Filter by PID
```
Tool: set_filters
Args: {"session_id": "abc12345", "process_pids": [12345]}
→ Only capture from specific process
```

### Step 9: Cleanup
```
Tool: destroy_session
Args: {"session_id": "abc12345"}
```

## Tips

1. **Create session first** - Always create a session before the target app starts to avoid missing early messages.

2. **Use `clear_session`** - After changing filters, clear the session to skip old messages.

3. **Poll with `since_seq`** - For continuous monitoring, use the `next_seq` value to get only new messages.

4. **Process filters are AND** - If you set both `process_names` and `process_pids`, entries must match both.

5. **Text filters are OR for include, AND for exclude** - Include matches if ANY pattern matches. Exclude rejects if ANY pattern matches.

6. **Regex patterns** - All filter patterns are Python regex. Remember to escape special characters like `[`, `]`, `.`, etc.

## Error Handling

Tool responses include `"error"` field on failure:

```json
{"error": "Session not found: xyz"}
{"error": "Invalid regex in include: [bad(pattern - ..."}
```

Always check for the `error` field in responses.
