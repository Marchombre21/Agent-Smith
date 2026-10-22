"""The limits of one task, as set by the subject."""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TaskLimits(BaseModel):
    """The four limits of one task (subject VI.1), plus a safety margin.

    The limits add up over the whole task, not per step. The agent stops
    at ``deadline_seconds``, a little before the subject's timeout, to
    leave time to write ``solution.json`` and exit cleanly.
    """

    model_config = ConfigDict(frozen=True)

    max_iterations: int = Field(..., gt=0, description="Agent steps allowed")
    max_input_tokens: int = Field(
        ..., gt=0, description="Input tokens allowed, summed over all steps"
    )
    max_output_tokens: int = Field(
        ..., gt=0, description="Output tokens allowed, summed over all steps"
    )
    timeout_seconds: float = Field(
        ..., gt=0, description="Wall-clock time allowed by the subject"
    )
    time_margin_seconds: float = Field(
        ...,
        ge=0,
        description="Time kept back from the timeout, to finish cleanly",
    )

    @model_validator(mode="after")
    def _check_margin(self) -> "TaskLimits":
        """Refuse a margin that leaves no time at all."""
        if self.time_margin_seconds >= self.timeout_seconds:
            raise ValueError("time_margin_seconds must be below the timeout")
        return self

    @property
    def deadline_seconds(self) -> float:
        """Seconds after the process start at which the agent must stop."""
        return self.timeout_seconds - self.time_margin_seconds

    @classmethod
    def mbpp(
        cls, max_iterations: int = 10, time_margin_seconds: float = 15.0
    ) -> "TaskLimits":
        """Build the limits of an MBPP task.

        Args:
            max_iterations: Steps allowed; configurable (subject V.3.4),
                but never above the subject's 10.
            time_margin_seconds: Time kept back from the 120 s timeout.

        Raises:
            ValueError: ``max_iterations`` is above the subject's limit.
        """
        return cls._within_subject(10, 6_000, 1_500, 120.0,
                                   max_iterations, time_margin_seconds)

    @classmethod
    def swebench(
        cls, max_iterations: int = 30, time_margin_seconds: float = 30.0
    ) -> "TaskLimits":
        """Build the limits of a SWE-bench task.

        Args:
            max_iterations: Steps allowed; configurable, but never above
                the subject's 30.
            time_margin_seconds: Time kept back from the 900 s timeout.

        Raises:
            ValueError: ``max_iterations`` is above the subject's limit.
        """
        return cls._within_subject(30, 300_000, 10_000, 900.0,
                                   max_iterations, time_margin_seconds)

    @classmethod
    def _within_subject(
        cls,
        subject_iterations: int,
        max_input_tokens: int,
        max_output_tokens: int,
        timeout_seconds: float,
        max_iterations: int,
        time_margin_seconds: float,
    ) -> "TaskLimits":
        """Build the limits, checking the steps against the subject's."""
        if max_iterations > subject_iterations:
            raise ValueError(
                f"max_iterations={max_iterations} is above the subject's "
                f"limit of {subject_iterations}"
            )
        return cls(
            max_iterations=max_iterations,
            max_input_tokens=max_input_tokens,
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
            time_margin_seconds=time_margin_seconds,
        )
