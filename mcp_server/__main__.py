# pyright: standard
"""Entry point for the RedDragon MCP server: uv run python -m mcp_server."""

from mcp_server.server import mcp

mcp.run()
