"""Data the extraction hands to the rest of the agent."""

from pydantic import BaseModel, ConfigDict, Field


class ExtractionResult(BaseModel):
    """The Python code found in one LLM answer, and how it was found.

    Whatever the format the model used (a Python block, an XML or JSON
    tool call, ReAct), the result is plain Python, so the sandbox never
    has to know about formats. ``warnings`` carries what the subject
    calls "malformed but interpreted anyway": the orchestrator adds them
    to the next observation so the model learns what was assumed.
    """

    model_config = ConfigDict(frozen=True)

    code: str | None = Field(
        description="Python to execute; None when nothing usable was found"
    )
    format_name: str = Field(
        description="Format the code came from, e.g. 'python' or 'hermes'"
    )
    warnings: tuple[str, ...] = Field(
        default=(),
        description="Messages for the LLM about what was repaired or "
        "assumed, e.g. a missing closing fence",
    )
