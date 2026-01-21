# Debug Capture MCP Server

An MCP (Model Context Protocol) server that enables AI to capture and filter Windows debug output (`OutputDebugString`).

## Components

- **dbgcapture/** - Headless C executable that captures Win32 debug output
- **mcp_server/** - Python MCP server exposing debug capture tools

## Requirements

- Windows 10/11
- Python 3.10+
- Visual Studio Build Tools (for compiling dbgcapture.exe)

## Building

### Build the capture executable

```cmd
cd MCP\dbgcapture
nmake
```

Or with Visual Studio Developer Command Prompt:
```cmd
cl /O2 dbgcapture.c /Fe:dbgcapture.exe advapi32.lib
```

### Install Python dependencies

```cmd
cd MCP\mcp_server
pip install -e .
```

## Usage

### Run the MCP server

```cmd
python -m dbgcapture_mcp
```

### MCP Tools

| Tool | Description |
|------|-------------|
| `create_session` | Create a new capture session with optional name |
| `destroy_session` | Destroy a capture session |
| `set_filters` | Set include/exclude regex filters and process filters |
| `get_output` | Get captured debug output (filtered) |
| `clear_session` | Clear session's read cursor to current position |
| `get_session_status` | Get session info: filters, pending count |
| `list_processes` | List running processes, optionally filtered by name |

## Architecture

```
MCP Client → MCP Server (Python) → Capture Manager → dbgcapture.exe
                  ↓
            Ring Buffer (shared)
                  ↓
            Session Views (filtered)
```

## License

Based on DebugView by Mark Russinovich / Sysinternals.
