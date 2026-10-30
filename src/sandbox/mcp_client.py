import asyncio
import shlex
from asyncio import AbstractEventLoop
from typing import Literal, Any
from fastmcp import Client
from fastmcp.client import StdioTransport
from fastmcp.exceptions import ToolError
from mcp.types import Tool
from src.sandbox.errors import (
    TransportSTDIOError,
    ServerMCPError,
    ToolExecutionError,
)


class MCPClient:
    """Init, connect and call tools af an MCP server. When it's done, close it
    gracefully.
    """

    def __init__(self, transport: Literal["stdio", "http"], address: str):
        """Init the MCP client by creating the async loop used to call mcp
        server's methods and connect with it by the asked transport

        Args:
            transport (Literal["stdio", "http"]): The
            wanted transport way (http or stdio)
            address (str): Whether the command to launch the server by stdio or
            the URL to connect http server
        """
        self.transport: Literal["stdio", "http"] = transport
        self.address: str = address
        self.loop: AbstractEventLoop = asyncio.new_event_loop()
        self.client: Client | None = self._create_client()

    def _create_client(self) -> Client:
        """Create client instance with wanted transport way."""
        match self.transport:
            case "stdio":
                cmd_parts = shlex.split(self.address)
                if len(cmd_parts) == 0 or cmd_parts[0].strip() == "":
                    raise TransportSTDIOError(
                        "The command to start the MCP server is missing"
                    )
                cmd_args = cmd_parts[1:]
                params = StdioTransport(command=cmd_parts[0], args=cmd_args)
                return Client(params)
            case "http":
                return Client(self.address)

    @property
    def _get_client(self) -> Client:
        if self.client:
            return self.client
        raise ServerMCPError("The MCP server isn't connected")

    def connect(self) -> None:
        """Try to connect the client to the server.

        Raises:
            ServerMCPError: In case the server can't be reached or the command
            doesn't exists and other reasons.
        """
        client = self._get_client
        try:
            self.loop.run_until_complete(client.__aenter__())
        except Exception as e:
            raise ServerMCPError(
                f"Cannot connect to the MCP server: {e}"
            ) from e

    def get_tools(self) -> list[Tool]:
        """Retrieve all tools available on the server."""
        client = self._get_client
        try:
            return self.loop.run_until_complete(client.list_tools())
        except Exception as e:
            raise ServerMCPError(f"Tool failed: {e}") from e

    def call_tool(self, name: str, args: dict[str, Any]) -> str | Any:
        """Call a tool on the server.

        Args:
            name (str): Name of the wanted tool
            args (dict[str, Any]): Args to add to the tool execution

        Returns:
            str | Any: The result of the tool execution
        """
        client = self._get_client
        try:
            result = self.loop.run_until_complete(
                client.call_tool(name=name, arguments=args)
            )
            if result.data is not None:
                return result.data
            else:
                return "\n".join(
                    c.text for c in result.content if hasattr(c, "text")
                )
        except ToolError as e:
            raise ToolExecutionError(f"Call tools failed: {e}") from e
        except Exception as e:
            raise ServerMCPError(
                f"MCP server failed during tool execution: {e}"
            ) from e

    def close(self) -> None:
        """Close the client and the loop properly."""
        if self.client is None:
            return
        try:
            self.loop.run_until_complete(self.client.close())
        except Exception:
            pass
        finally:
            self.client = None
            self.loop.close()
