import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPClientManager:
    """Persistent MCP client manager for the local tool servers."""

    SERVER_FILES = {
        "rag": "rag_mcp_server.py",
        "code_exec": "code_exec_mcp_server.py",
        "calculator": "calculator_mcp_server.py",
    }

    def __init__(self):
        self._stack = AsyncExitStack()
        self._sessions = {}
        self.tools = {}
        self._initialized = False

    async def initialize(self):
        if self._initialized:
            return

        backend_dir = Path(__file__).resolve().parents[1]
        servers_dir = backend_dir / "servers"

        for server_name, filename in self.SERVER_FILES.items():
            server_path = servers_dir / filename
            params = StdioServerParameters(
                command=sys.executable,
                args=[str(server_path)],
                cwd=str(backend_dir),
                env={
                    **os.environ,
                    "PYTHONPATH": str(backend_dir),
                },
            )

            print(f"[MCP] Connecting to {server_name} server: {server_path.name}")
            read_stream, write_stream = await self._stack.enter_async_context(
                stdio_client(params)
            )
            session = await self._stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )

            await session.initialize()
            response = await session.list_tools()
            self._sessions[server_name] = session

            for tool in response.tools:
                self.tools[tool.name] = {
                    "server": server_name,
                    "description": tool.description or "",
                    "input_schema": getattr(
                        tool, "inputSchema",
                        getattr(tool, "input_schema", {}),
                    ),
                }

            print(
                f"[MCP] {server_name}: discovered tools -> "
                f"{[tool.name for tool in response.tools]}"
            )

        self._initialized = True
        print(f"[MCP] Total discovered tools: {list(self.tools)}")

    async def call_tool(self, tool_name: str, arguments: dict):
        if not self._initialized:
            await self.initialize()

        if tool_name not in self.tools:
            raise ValueError(f"MCP tool '{tool_name}' was not discovered.")

        server_name = self.tools[tool_name]["server"]
        session = self._sessions[server_name]

        print(f"[MCP] Calling '{tool_name}' on {server_name} server")
        result = await session.call_tool(tool_name, arguments=arguments)
        print(f"[MCP] Tool '{tool_name}' completed")
        return result

    async def close(self):
        if not self._initialized:
            return

        print("[MCP] Closing MCP server sessions")
        await self._stack.aclose()
        self._sessions.clear()
        self.tools.clear()
        self._initialized = False
