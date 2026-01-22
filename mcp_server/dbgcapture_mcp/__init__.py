"""
Debug Capture MCP Server

Provides MCP tools for capturing and filtering Windows debug output.
"""

__version__ = "0.1.0"

from .server import main, create_server

__all__ = ["__version__", "main", "create_server"]
