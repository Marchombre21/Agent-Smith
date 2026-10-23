"""Turn what happened at one step into the text the LLM reads next."""

from typing import List, Optional

from src.extraction.base import ExtractionResult
from src.sandbox_port import ExecutionResult


class ObservationFormatter:
    """Write the observation of one step from raw facts.

    The sandbox reports facts only (``ExecutionResult``); the sentences
    the LLM reads are written here, so that every case the subject lists
    gets explicit feedback: no code found, code repaired, partial output
    after a timeout, truncated output. The ``Observation:`` prefix is
    added by ``Conversation``, not here.
    """

    _NO_OUTPUT = "(no output)"
    _TRUNCATED = "[Output truncated: too long.]"
    _TIMED_OUT = (
        "Execution stopped: time limit reached. The output above is partial."
    )
    _MEMORY_EXCEEDED = "Execution stopped: memory limit reached."
    _ERROR_HEADER = "Error:"
    _STATE_RESET = (
        "Variables from previous steps were lost: define them again."
    )
    _CUT_MARKER = "\n[... {cut} characters cut ...]\n"
    # Characters kept free for the marker, so the result fits max_chars.
    _MARKER_ROOM = 40

    # Provisoire : filet de sécurité tant que le contrat #9 (qui tronque,
    # et à combien) est ouvert ; 2 000 caractères pour MBPP, à mesurer.
    def __init__(self, max_chars: int = 2000) -> None:
        """Set the longest observation the LLM may receive.

        Args:
            max_chars: Length limit of the whole observation, marker
                included; a longer one keeps its start and its end.

        Raises:
            ValueError: ``max_chars`` leaves no room for any text.
        """
        if max_chars <= self._MARKER_ROOM:
            raise ValueError(
                f"max_chars={max_chars} must be above {self._MARKER_ROOM}"
            )
        self._max_chars = max_chars

    def format(
        self,
        extraction: ExtractionResult,
        result: Optional[ExecutionResult],
    ) -> str:
        """Build the observation text.

        Extraction warnings come first, so the model learns what was
        assumed about its code before reading what the code did.

        Args:
            extraction: What was found in the model's answer.
            result: What the sandbox reported; None when no code was
                run, in which case the extraction warnings say why.
        """
        parts: List[str] = list(extraction.warnings)
        if result is None:
            return self._shorten("\n".join(parts))
        parts.append(result.stdout.rstrip("\n") or self._NO_OUTPUT)
        if result.truncated:
            parts.append(self._TRUNCATED)
        if result.timed_out:
            parts.append(self._TIMED_OUT)
        if result.memory_exceeded:
            parts.append(self._MEMORY_EXCEEDED)
        if result.error is not None:
            parts.append(self._ERROR_HEADER)
            parts.append(result.error.rstrip("\n"))
        if result.state_reset:
            parts.append(self._STATE_RESET)
        return self._shorten("\n".join(parts))

    def _shorten(self, text: str) -> str:
        """Cut the middle of ``text`` if it is longer than ``max_chars``.

        The start gives the context (extraction warnings, first lines of
        output) and the end the outcome (last line of a traceback, the
        timeout message), so the middle is what goes.
        """
        if len(text) <= self._max_chars:
            return text
        kept = self._max_chars - self._MARKER_ROOM
        head = kept // 2
        tail = kept - head
        marker = self._CUT_MARKER.format(cut=len(text) - kept)
        return text[:head] + marker + text[len(text) - tail:]
