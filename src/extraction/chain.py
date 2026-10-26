"""The extraction step as the orchestrator sees it: one call, one result."""

from collections.abc import Sequence

from src.extraction.base import CodeExtractor
from src.extraction.models import ExtractionResult
from src.extraction.hermes import HermesExtractor
from src.extraction.python_block import PythonBlockExtractor
from src.extraction.react import ReActExtractor
from src.extraction.xml_invoke import XmlExtractor


class CodeExtraction:
    """Tries each extractor in turn on the LLM's answer.

    The first extractor that recognises its format decides: its result
    is returned as is, code or broken call alike. Unlike an extractor,
    this class always returns a result, so the orchestrator never has to
    handle None.
    """

    # Observation sent when no format was recognised. Keep it in line
    # with the example given in the system prompt.
    _NO_CODE = (
        "No code was found in your answer, so nothing was run.\n"
        "Write your code in one block, then stop:\n"
        "```python\n"
        "...\n"
        "```<end_code>"
    )

    def __init__(self, extractors: Sequence[CodeExtractor]) -> None:
        """Keep the extractors, in the order they will be tried.

        Raises:
            ValueError: ``extractors`` is empty; such a chain would never
                find anything.
        """
        if not extractors:
            raise ValueError("extractors must not be empty")
        self._extractors = tuple(extractors)

    @classmethod
    def default(cls) -> "CodeExtraction":
        """Build the chain used by the agents.

        The Python block comes first, as the primary format; then the
        tool call formats, from the strictest to the loosest, so that a
        stray "Action:" line is the last thing considered.
        """
        return cls(
            [
                PythonBlockExtractor(),
                HermesExtractor(),
                XmlExtractor(),
                ReActExtractor(),
            ]
        )

    def extract(self, text: str) -> ExtractionResult:
        """Return the code of the LLM's answer, from the first format found.

        Returns:
            The first extractor's result that is not None, as is; when
            no format is recognised, a result without code whose warning
            tells the LLM what is expected.
        """
        for extractor in self._extractors:
            result = extractor.extract(text)
            if result is not None:
                return result
        return ExtractionResult(
            code=None, format_name="none", warnings=(self._NO_CODE,)
        )
