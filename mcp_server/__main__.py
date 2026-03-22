"""Entry point for the RedDragon MCP server: poetry run python -m mcp_server."""

import asyncio

from mcp_server.server import mcp

asyncio.run(mcp.run())
