"""What one task has used of its limits, and what is left of them."""

import time
from collections.abc import Callable
from typing import Optional

from src.orchestrator.models import TaskLimits


class TaskBudget:
    """What one task has used of its limits so far, and what is left.

    The clock starts when the process starts, not at the first LLM call:
    the moulinette counts the launch of ``uv`` and the imports too.
    Time is read through an injectable ``clock`` (``time.monotonic`` by
    default), so tests can move time forward by hand.
    """

    def __init__(
        self,
        limits: TaskLimits,
        started_at: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Start a budget with nothing used.

        Args:
            limits: The limits of the task.
            started_at: Value of ``clock`` when the process started.
            clock: Returns the current time in seconds.
        """
        self._limits = limits
        self._started_at = started_at
        self._clock = clock
        self._iterations = 0
        self._input_tokens = 0
        self._output_tokens = 0

    def record_step(self, input_tokens: int, output_tokens: int) -> None:
        """Count one finished step and the tokens its LLM call used.

        Args:
            input_tokens: Input tokens of the call, as counted by the
                provider.
            output_tokens: Output tokens of the call, idem.
        """
        self._iterations += 1
        self._input_tokens += input_tokens
        self._output_tokens += output_tokens

    @property
    def limits(self) -> TaskLimits:
        """The limits this budget counts against."""
        return self._limits

    @property
    def iterations(self) -> int:
        """Steps recorded so far."""
        return self._iterations

    @property
    def input_tokens(self) -> int:
        """Input tokens used so far, summed over all steps."""
        return self._input_tokens

    @property
    def output_tokens(self) -> int:
        """Output tokens used so far, summed over all steps."""
        return self._output_tokens

    @property
    def elapsed_seconds(self) -> float:
        """Seconds since the process started."""
        return self._clock() - self._started_at

    @property
    def remaining_input_tokens(self) -> int:
        """Input tokens still allowed."""
        return max(0, self._limits.max_input_tokens - self._input_tokens)

    @property
    def remaining_output_tokens(self) -> int:
        """Output tokens still allowed: the ``max_tokens`` of next call."""
        return max(0, self._limits.max_output_tokens - self._output_tokens)

    @property
    def remaining_seconds(self) -> float:
        """Seconds left before the deadline (margin already taken off)."""
        return max(0.0, self._limits.deadline_seconds - self.elapsed_seconds)

    def stop_reason(self) -> Optional[str]:
        """Say why the task must stop now, or None if it can go on.

        Checked before each step. The text is meant for
        ``SolutionOutput.error``.
        """
        limits = self._limits
        if self.remaining_seconds <= 0:
            return (f"time limit reached ({limits.deadline_seconds:g} s "
                    f"of {limits.timeout_seconds:g} s, margin kept)")
        if self._iterations >= limits.max_iterations:
            return f"iteration limit reached ({limits.max_iterations})"
        if self.remaining_input_tokens <= 0:
            return (f"input token limit reached "
                    f"({limits.max_input_tokens})")
        if self.remaining_output_tokens <= 0:
            return (f"output token limit reached "
                    f"({limits.max_output_tokens})")
        return None

    def can_afford(self, estimated_input_tokens: int) -> bool:
        """Tell whether the next LLM call fits in the input tokens left.

        Each call sends the whole conversation again, so its input grows
        at every step; it is estimated before the call, and a call that
        would go over the limit is not made.

        Args:
            estimated_input_tokens: Estimated input of the next call.
        """
        return estimated_input_tokens <= self.remaining_input_tokens
