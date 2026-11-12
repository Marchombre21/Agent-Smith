"""Turn what happened at one step into the text the LLM reads next."""

from typing import List, Optional

from src.extraction.models import ExtractionResult
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
    _SILENT_RUN = "The code ran without error and printed nothing."
    # The loop stops right after this step: the model never reads it, but
    # solution.json does, and must say what really happened.
    _FINAL_ANSWER = "final_answer() was called: the task ends here."
    _TIMED_OUT = (
        "Execution stopped: time limit reached. The output above is partial."
    )
    _MEMORY_EXCEEDED = "Execution stopped: memory limit reached."
    _ERROR_HEADER = "Error:"
    _STATE_RESET = (
        "Variables from previous steps were lost: define them again."
    )
    _REPEATED = (
        "Same code and same result as step {step}. Sending it again will "
        "not help: try something different."
    )

    _ANSWER_CUT = (
        "Your answer was cut after {tokens} tokens, so its end is missing. "
        "Write a shorter answer."
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
        repeat_of: Optional[int] = None,
        cut_at: Optional[int] = None,
    ) -> str:
        """Build the observation text.

        Extraction warnings come first, so the model learns what was
        assumed about its code before reading what the code did. The
        cut-answer and repetition notices come last: a long observation
        keeps its end.

        Args:
            extraction: What was found in the model's answer.
            result: What the sandbox reported; None when no code was
                run, in which case the extraction warnings say why.
            repeat_of: Number of the earlier step that had the same code
                and the same result (``RepeatDetector``), or None. Not
                used when no code was run.
            cut_at: Output tokens of the answer when the LLM was stopped
                by its token limit, or None. Reported even when no code
                was run: it explains why none was found.
        """
        parts: List[str] = list(extraction.warnings)
        if result is None:
            if cut_at is not None:
                parts.append(self._ANSWER_CUT.format(tokens=cut_at))
            return self._shorten("\n".join(parts))
        clean = result.error is None and not (
            result.timed_out or result.memory_exceeded
        )
        output = result.stdout.rstrip("\n")
        if result.final_answer is not None:
            # What was printed before the call is kept; no "printed
            # nothing" sentence, the call itself is the outcome.
            if output:
                parts.append(output)
            parts.append(self._FINAL_ANSWER)
        else:
            empty = self._SILENT_RUN if clean else self._NO_OUTPUT
            parts.append(output or empty)
        if result.timed_out:
            parts.append(self._TIMED_OUT)
        if result.memory_exceeded:
            parts.append(self._MEMORY_EXCEEDED)
        if result.error is not None:
            parts.append(self._ERROR_HEADER)
            parts.append(result.error.rstrip("\n"))
        if result.state_reset:
            parts.append(self._STATE_RESET)
        if cut_at is not None:
            parts.append(self._ANSWER_CUT.format(tokens=cut_at))
        if repeat_of is not None:
            parts.append(self._REPEATED.format(step=repeat_of))
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
