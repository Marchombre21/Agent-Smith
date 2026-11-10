"""Spot a step that sends the same code and gets the same result again."""

from typing import Optional


class RepeatDetector:
    """Remember what each code gave, to notice a loop.

    Sending the same code twice is not always a mistake: after an edit,
    reading the same lines again shows the new content. What blocks the
    model is the same code giving the same result (the same failed edit
    with the same error, for instance). Only that case is reported.

    Two codes that differ only by indentation, blank lines or trailing
    spaces count as the same: the model often resends a call with its
    spacing changed.
    """

    def __init__(self) -> None:
        """Start with no step seen."""
        # Normalised code -> (step, observation) of its latest run.
        self._seen: dict[str, tuple[int, str]] = {}

    def check(self, step: int, code: str, observation: str) -> Optional[int]:
        """Say whether this step repeats the latest run of the same code.

        The step is remembered either way, so a third identical step is
        compared with the second one.

        Args:
            step: Number of the step that has just run.
            code: The code the model sent at that step.
            observation: What that code gave, as the model would read it.

        Returns:
            The number of the earlier step with the same code and the
            same result, or None if this is new or the result differs.
        """
        key = self._normalize(code)
        earlier = self._seen.get(key)
        self._seen[key] = (step, observation)
        if earlier is not None and earlier[1] == observation:
            return earlier[0]
        return None

    @staticmethod
    def _normalize(code: str) -> str:
        """Drop indentation, trailing spaces and blank lines of ``code``."""
        lines = (line.strip() for line in code.splitlines())
        return "\n".join(line for line in lines if line)
