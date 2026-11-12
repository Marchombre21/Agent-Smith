"""Spot a step that sends the same code and gets the same result again."""

import re
from typing import Optional


class RepeatDetector:
    """Remember what each code gave, to notice a loop.

    Sending the same code twice is not always a mistake: after an edit,
    reading the same lines again shows the new content. What blocks the
    model is the same code giving the same result (the same failed edit
    with the same error, for instance). Only that case is reported.

    Two codes that differ only by indentation, blank lines or trailing
    spaces count as the same: the model often resends a call with its
    spacing changed. Results are compared without their noise (random
    seeds, durations): two runs of the same tests never print the same
    seed. Counts stay: "44 passed" then "45 passed" is progress, not a
    repeat.
    """

    # What changes from one run to the next with nothing new to learn.
    _NOISE = re.compile(
        r"random seed:\s*\d+"
        r"|PYTHONHASHSEED=\d+"
        r"|\b\d+(?:\.\d+)?\s?(?:seconds|s)\b"
    )

    def __init__(self, enabled: bool = True) -> None:
        """Start with no step seen.

        Args:
            enabled: False turns the detector off (``check`` never
                reports a repeat). Used by the ablation of the detector.
        """
        self._enabled = enabled
        # Normalised code -> (step, result without noise) of its latest run.
        self._seen: dict[str, tuple[int, str]] = {}

    def check(self, step: int, code: str, result: str) -> Optional[int]:
        """Say whether this step repeats the latest run of the same code.

        The step is remembered either way, so a third identical step is
        compared with the second one.

        Args:
            step: Number of the step that has just run.
            code: The code the model sent at that step.
            result: What that code gave: the raw output and error of
                the sandbox, before any cut or sentence is added (the
                cut moves with the length of the output).

        Returns:
            The number of the earlier step with the same code and the
            same result, or None if this is new, the result differs or
            the detector is off.
        """
        if not self._enabled:
            return None
        key = self._normalize(code)
        earlier = self._seen.get(key)
        outcome = self._NOISE.sub("#", result)
        self._seen[key] = (step, outcome)
        if earlier is not None and earlier[1] == outcome:
            return earlier[0]
        return None

    @staticmethod
    def _normalize(code: str) -> str:
        """Drop indentation, trailing spaces and blank lines of ``code``."""
        lines = (line.strip() for line in code.splitlines())
        return "\n".join(line for line in lines if line)
