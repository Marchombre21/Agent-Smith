"""The interface every code extractor shares."""

from abc import ABC, abstractmethod

from src.extraction.models import ExtractionResult


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
