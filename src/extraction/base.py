"""What every code extractor returns, and the interface they share."""

from abc import ABC, abstractmethod

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


class CodeExtractor(ABC):
    """Recognises one answer format and turns it into Python.

    Extractors are tried in turn by the orchestrator's extraction chain:
    each one either claims the answer or steps aside, so a new format is
    supported by writing one subclass and adding it to the chain.
    """

    @abstractmethod
    def extract(self, text: str) -> ExtractionResult | None:
        """Look for this extractor's format in the LLM's answer.

        Args:
            text: The model's raw answer (``LLMResponse.text``); the stop
                sequence, e.g. ``<end_code>``, is already cut off.

        Returns:
            The code found, with warnings if the format had to be
            repaired; None when the format is absent, so that the next
            extractor gets a chance.
        """
