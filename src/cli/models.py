"""Settings of an agent, read from its file in ``configs/``."""

from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

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
    max_observation_chars: int = Field(
        default=2000,
        gt=0,
        description="Longest observation sent to the LLM; a longer one "
        "keeps its start and its end (ObservationFormatter)",
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
        description="Limits and allowlists of the sandbox, or the path of "
        "the JSON file that holds them (configs/sandbox_*.json)",
    )

    @field_validator("sandbox", mode="before")
    @classmethod
    def _read_sandbox_file(cls, value: Any) -> Any:
        """Read the sandbox config from its file when given a path.

        One file per benchmark, shared with the sandbox REPL
        (``uv run sandbox configs/sandbox_mbpp.json``), so that the agent
        and the REPL run the same sandbox. A path is relative to the
        current directory: the moulinette runs the agent from the root
        of the repository.

        Raises:
            OSError: the file cannot be read (not wrapped by pydantic, so
                ``BenchmarkCli.launch`` reports it like a missing settings
                file).
            ValueError: the file is not a valid ``SandboxConfig``.
        """
        if isinstance(value, str):
            return SandboxConfig.model_validate_json(
                Path(value).read_text(encoding="utf-8")
            )
        return value

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
