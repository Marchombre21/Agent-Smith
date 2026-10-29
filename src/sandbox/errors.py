from src.sandbox_port import SandboxError


class TemplateError(Exception):
    """Raised when the sandbox configuration file is invalid."""


class TransportSTDIOError(SandboxError):
    """Raised when the command to launch the mcp server is invalid."""


class ServerMCPError(SandboxError):
    """Raised when the mcp server failed."""


class ToolExecutionError(Exception):
    """Raised when the tool execution failed in the mcp server."""
