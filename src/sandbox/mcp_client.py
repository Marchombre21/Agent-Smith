import asyncio
import shlex
import textwrap
from asyncio import AbstractEventLoop
from typing import Literal, Any
from fastmcp import Client
from fastmcp.client import StdioTransport
from fastmcp.exceptions import ToolError, McpError
from mcp.types import (
    Tool,
    Prompt,
    GetPromptResult,
    Resource,
    ResourceTemplate,
    TextResourceContents,
    BlobResourceContents,
    TextContent,
)
from src.sandbox.errors import (
    TransportSTDIOError,
    ServerMCPError,
    ToolExecutionError,
    ResourcesError,
    PromptError,
)


class MCPClient:
    """Init, connect and call tools af an MCP server. When it's done, close it
    gracefully.
    """

    def __init__(
        self,
        transport: Literal["stdio", "http"],
        address: str,
        env: dict[str, Any] | None,
    ):
        """Init the MCP client by creating the async loop used to call mcp
        server's methods and connect with it by the asked transport

        Args:
            transport (Literal["stdio", "http"]): The
            wanted transport way (http or stdio)
            address (str): Whether the command to launch the server by stdio or
            the URL to connect http server
            env (dict[str, str] | None): Environment variables passed to the
            stdio server process.
        """
        self.transport: Literal["stdio", "http"] = transport
        self.address: str = address
        self.env = env
        self.loop: AbstractEventLoop = asyncio.new_event_loop()
        self.client: Client[Any] | None = self._create_client()

    def _create_client(self) -> Client[Any]:
        """Create client instance with wanted transport way."""
        match self.transport:
            case "stdio":
                cmd_parts = shlex.split(self.address)
                if len(cmd_parts) == 0 or cmd_parts[0].strip() == "":
                    raise TransportSTDIOError(
                        "The command to start the MCP server is missing"
                    )
                cmd_args = cmd_parts[1:]
                params = StdioTransport(
                    command=cmd_parts[0],
                    args=cmd_args,
                    env=self.env,
                )
                return Client(params)
            case "http":
                return Client(self.address)

    @property
    def _get_client(self) -> Client[Any]:
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

    def get_prompts(self) -> list[Prompt]:
        """Retrieve all prompts available on the server."""
        client = self._get_client
        try:
            return self.loop.run_until_complete(client.list_prompts())
        except Exception as e:
            raise ServerMCPError(f"Prompts retrieval failed: {e}") from e

    def get_resources(self) -> tuple[list[Resource], list[ResourceTemplate]]:
        """Retrieve all resources available on the server."""
        client = self._get_client
        try:
            resources = self.loop.run_until_complete(client.list_resources())
            resources_temp = self.loop.run_until_complete(
                client.list_resource_templates()
            )
            return (resources, resources_temp)
        except McpError:
            return ([], [])

    def retrieve_prompt(
        self, name: str, args: dict[str, str] | None = None
    ) -> str:
        """Read and return an exposed prompt on the server.

        Args:
            name (str): The name of the wanted prompt.
            args (dict[str, Any]): The arguments needed to get the wanted
            prompt.
        """
        client: Client = self._get_client
        try:
            result: GetPromptResult = self.loop.run_until_complete(
                client.get_prompt(name, args)
            )
            final_result: list[str] = []
            for i, message in enumerate(result.messages):
                content: str = textwrap.indent(
                    (
                        message.content.text
                        if isinstance(message.content, TextContent)
                        else "Not a text content. Impossible to display."
                    ),
                    "        ",
                ).lstrip()
                final_result.append(f"Message {i + 1}:")
                final_result.append(f"    Role: {message.role}")
                final_result.append(f"    Content: {content}")
            return "\n".join(final_result)
        except (McpError, ValueError) as e:
            raise PromptError(f"Prompt retrieval failed: {e}") from e
        except Exception as e:
            raise ServerMCPError(
                f"MCP server failed during prompt retrieval: {e}"
            ) from e

    def read_resource(self, uri: str) -> str:
        """Read and return an exposed resource on the server.

        Args:
            uri (str): The uri of the wanted resource.
        """
        client: Client = self._get_client
        try:
            result = self.loop.run_until_complete(client.read_resource(uri))
            final_result: list[str] = []
            for elem in result:
                if isinstance(elem, TextResourceContents):
                    final_result.append(elem.text)
                if isinstance(elem, BlobResourceContents):
                    final_result.append(f"[binary content]: {elem.mimeType}")
            return "\n".join(final_result)
        except (McpError, ValueError) as e:
            raise ResourcesError(f"Resources retrieval failed: {e}") from e
        except Exception as e:
            raise ServerMCPError(
                f"MCP server failed during resource retrieval: {e}"
            ) from e

    def call_tool(
        self, name: str, args: dict[str, Any]
    ) -> str:
        """Call a tool on the server.

        Args:
            name (str): Name of the wanted tool
            args (dict[str, Any]): Args to add to the tool execution

        Returns:
            str: The result of the tool execution
        """
        client = self._get_client
        try:
            result = self.loop.run_until_complete(
                client.call_tool(name=name, arguments=args)
            )
            content_res: list[str] = []
            for content in result.content:
                if isinstance(content, TextContent):
                    content_res.append(content.text)
                else:
                    content_res.append(
                        "Not a text content. Impossible to display."
                    )
            if not content_res:
                return "The tool has no response to return."
            return "\n".join(content_res)
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
