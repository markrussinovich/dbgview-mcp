# Debug Capture MCP Server

An MCP (Model Context Protocol) server that enables AI to capture and filter Windows debug output (`OutputDebugString`).

[![PyPI version](https://badge.fury.io/py/dbgview-mcp.svg)](https://pypi.org/project/dbgview-mcp/)
[![Test](https://github.com/markrussinovich/dbgview-mcp/actions/workflows/test.yml/badge.svg)](https://github.com/markrussinovich/dbgview-mcp/actions/workflows/test.yml)

## Installation

### From PyPI (recommended)

```cmd
pip install dbgview-mcp
```

The package includes the pre-built `dbgcapture.exe` binary.

### From source

```cmd
git clone https://github.com/markrussinovich/dbgview-mcp.git
cd dbgview-mcp/mcp_server
pip install -e .
```

When installing from source, you'll need to build `dbgcapture.exe` (see [Building from Source](#building-from-source) below).

## Components

- **dbgcapture/** - Headless C executable that captures Win32 debug output
- **mcp_server/** - Python MCP server exposing debug capture tools

## Requirements

- Windows 10/11
- Python 3.10+

## Building from Source

### Build the capture executable

Requires Visual Studio Build Tools:

```cmd
cd dbgcapture
nmake
```

Or with Visual Studio Developer Command Prompt:
```cmd
cl /O2 dbgcapture.c /Fe:dbgcapture.exe advapi32.lib
```

### Install Python dependencies

```cmd
cd mcp_server
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

MIT License - see [LICENSE](LICENSE) for details.

Inspired by DebugView by Mark Russinovich / Sysinternals.
