"""Settings of an agent, read from its file in ``configs/``."""

from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.models import SandboxConfig


class AgentSettings(BaseModel):
    """What an agent uses when the command line does not say otherwise.

    One file per agent (``configs/agent_mbpp.json``…), so that changing
    the default model or a margin needs no change in the code. The
    provider is given by name, not by URL: the Cloudflare URL holds an
    account id that must not be versioned.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str = Field(..., description="Default provider, by name")
    model_name: str = Field(..., description="Default model of that provider")
    max_iterations: int = Field(..., gt=0, description="Agent steps allowed")
    time_margin_seconds: float = Field(
        ..., ge=0, description="Time kept back from the subject's timeout"
    )
    keep_last_observations: Optional[int] = Field(
        ...,
        ge=0,
        description="Observations sent in full; older ones are shortened. "
        "None keeps them all",
    )
    transport: Optional[Literal["stdio", "http"]] = Field(
        default=None, description="How the sandbox reaches the MCP server"
    )
    address: Optional[str] = Field(
        default=None,
        description="Command that starts the server (stdio) or its URL "
        "(http)",
    )
    sandbox: SandboxConfig = Field(
        default_factory=SandboxConfig,
        description="Limits and allowlists of the sandbox",
    )

    @model_validator(mode="after")
    def _check_mcp(self) -> "AgentSettings":
        """Refuse a transport without an address, or the reverse."""
        if (self.transport is None) != (self.address is None):
            raise ValueError("transport and address go together")
        return self

    @classmethod
    def from_file(cls, path: Path) -> "AgentSettings":
        """Read the settings of an agent from a JSON file.

        Raises:
            OSError: the file cannot be read.
            pydantic.ValidationError: the JSON is malformed, a field is
                missing, unknown or invalid.
        """
        return cls.model_validate_json(path.read_text(encoding="utf-8"))
