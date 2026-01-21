"""
Debug Capture MCP Server

Provides MCP tools for capturing and filtering Windows debug output.
"""

from .server import main, create_server

__all__ = ["main", "create_server"]
