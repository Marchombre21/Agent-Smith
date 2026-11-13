from src.sandbox_port import SandboxError


class TemplateError(Exception):
    """Raised when the sandbox configuration file is invalid."""


class TransportSTDIOError(SandboxError):
    """Raised when the command to launch the mcp server is invalid."""


class ServerMCPError(SandboxError):
    """Raised when the mcp server failed."""


class ToolExecutionError(Exception):
    """Raised when the tool execution failed in the mcp server."""


class ResourcesError(Exception):
    """Raised when the resources retrieval failed in the mcp server."""


class ProtocolError(Exception):
    """Raised when the sandbox receives a message from the worker that does
    not comply with the established communication protocol."""
