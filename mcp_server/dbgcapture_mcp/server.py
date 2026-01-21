"""
MCP Server for Debug Capture

Exposes debug capture functionality via MCP tools.
"""

import argparse
import asyncio
import json
import re
import traceback
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .capture_manager import get_manager


def create_server() -> Server:
    """Create and configure the MCP server."""
    server = Server("dbgcapture-mcp")
    
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """Return the list of available tools."""
        return [
            Tool(
                name="create_session",
                description="Create a new debug capture session. Returns a session_id for use with other tools. Capture starts automatically on first session.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Optional friendly name for the session"
                        }
                    }
                }
            ),
            Tool(
                name="destroy_session",
                description="Destroy a debug capture session. Capture stops when last session is destroyed.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "The session ID to destroy"
                        }
                    },
                    "required": ["session_id"]
                }
            ),
            Tool(
                name="set_filters",
                description="Set filters for a capture session. Filters are regex patterns. Include patterns show matching entries; exclude patterns hide them. Process filters limit to specific processes.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "The session ID"
                        },
                        "include": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Regex patterns - entries must match at least one to be included. Empty = include all."
                        },
                        "exclude": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Regex patterns - entries matching any pattern are excluded"
                        },
                        "process_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Regex patterns for process names to capture from"
                        },
                        "process_pids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Specific PIDs to capture from"
                        }
                    },
                    "required": ["session_id"]
                }
            ),
            Tool(
                name="get_output",
                description="Get captured debug output for a session. Returns entries that match the session's filters. Use since_seq to get only new entries since last call.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "The session ID"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum entries to return (default 100)",
                            "default": 100
                        },
                        "since_seq": {
                            "type": "integer",
                            "description": "Only return entries after this sequence number"
                        }
                    },
                    "required": ["session_id"]
                }
            ),
            Tool(
                name="clear_session",
                description="Clear session's read position - skip all pending entries and start fresh from now.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "The session ID"
                        }
                    },
                    "required": ["session_id"]
                }
            ),
            Tool(
                name="get_session_status",
                description="Get status of a capture session including active filters, pending entry count, and capture state.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "The session ID"
                        }
                    },
                    "required": ["session_id"]
                }
            ),
            Tool(
                name="list_processes",
                description="List running processes. Useful for finding PIDs to filter by.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name_pattern": {
                            "type": "string",
                            "description": "Optional regex pattern to filter process names"
                        }
                    }
                }
            ),
            Tool(
                name="list_sessions",
                description="List all active capture sessions.",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            )
        ]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle tool calls."""
        manager = get_manager()
        
        try:
            if name == "create_session":
                session_name = arguments.get("name")
                session_id = manager.create_session(session_name)
                return [TextContent(
                    type="text",
                    text=f'{{"session_id": "{session_id}", "status": "created", "capture_running": true}}'
                )]
            
            elif name == "destroy_session":
                session_id = arguments["session_id"]
                success = manager.destroy_session(session_id)
                if success:
                    return [TextContent(
                        type="text",
                        text=f'{{"session_id": "{session_id}", "status": "destroyed"}}'
                    )]
                else:
                    return [TextContent(
                        type="text",
                        text=f'{{"error": "Session not found: {session_id}"}}'
                    )]
            
            elif name == "set_filters":
                session_id = arguments["session_id"]
                
                # Validate regex patterns before applying
                for field in ["include", "exclude", "process_names"]:
                    patterns = arguments.get(field, [])
                    for p in patterns:
                        try:
                            re.compile(p)
                        except re.error as e:
                            return [TextContent(
                                type="text",
                                text=f'{{"error": "Invalid regex in {field}: {p} - {e}"}}'
                            )]
                
                success = manager.set_filters(
                    session_id,
                    include=arguments.get("include"),
                    exclude=arguments.get("exclude"),
                    process_names=arguments.get("process_names"),
                    process_pids=arguments.get("process_pids")
                )
                
                if success:
                    status = manager.get_session_status(session_id)
                    return [TextContent(
                        type="text",
                        text=json.dumps({"status": "filters_set", "filters": status["filters"]})
                    )]
                else:
                    return [TextContent(
                        type="text",
                        text=f'{{"error": "Session not found: {session_id}"}}'
                    )]
            
            elif name == "get_output":
                session_id = arguments["session_id"]
                limit = arguments.get("limit", 100)
                since_seq = arguments.get("since_seq")
                
                entries, next_seq = manager.get_output(session_id, limit, since_seq)
                
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "entries": entries,
                        "count": len(entries),
                        "next_seq": next_seq
                    })
                )]
            
            elif name == "clear_session":
                session_id = arguments["session_id"]
                success = manager.clear_session(session_id)
                if success:
                    return [TextContent(
                        type="text",
                        text=f'{{"session_id": "{session_id}", "status": "cleared"}}'
                    )]
                else:
                    return [TextContent(
                        type="text",
                        text=f'{{"error": "Session not found: {session_id}"}}'
                    )]
            
            elif name == "get_session_status":
                session_id = arguments["session_id"]
                status = manager.get_session_status(session_id)
                
                if status:
                    return [TextContent(
                        type="text",
                        text=json.dumps(status)
                    )]
                else:
                    return [TextContent(
                        type="text",
                        text=f'{{"error": "Session not found: {session_id}"}}'
                    )]
            
            elif name == "list_processes":
                name_pattern = arguments.get("name_pattern")
                processes = manager.list_processes(name_pattern)
                
                return [TextContent(
                    type="text",
                    text=json.dumps({"processes": processes, "count": len(processes)})
                )]
            
            elif name == "list_sessions":
                sessions = []
                with manager._sessions_lock:
                    for session in manager._sessions.values():
                        sessions.append({
                            "session_id": session.id,
                            "name": session.name,
                            "cursor": session.cursor
                        })
                
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "sessions": sessions,
                        "count": len(sessions),
                        "capture_running": manager.is_running()
                    })
                )]
            
            else:
                return [TextContent(
                    type="text",
                    text=f'{{"error": "Unknown tool: {name}"}}'
                )]
                
        except Exception as e:
            return [TextContent(
                type="text",
                text=f'{{"error": "{str(e)}", "traceback": "{traceback.format_exc()}"}}'
            )]
    
    return server


async def run_server():
    """Run the MCP server."""
    server = create_server()
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="dbgcapture-mcp",
        description="MCP server for capturing Windows debug output (OutputDebugString)"
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0"
    )
    parser.parse_args()
    
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
