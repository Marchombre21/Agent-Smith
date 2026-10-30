"""The command line of the MBPP agent (``python -m agent_mbpp``)."""

from pathlib import Path
from typing import Literal

from src.cli.base import BenchmarkCli
from src.cli.mbpp_task import MbppTask
from src.orchestrator.models import TaskLimits


class MbppCli(BenchmarkCli):
    """Solve one MBPP task: everything else comes from ``BenchmarkCli``."""

    def _benchmark(self) -> Literal["mbpp", "swebench"]:
        """Return ``"mbpp"``."""
        return "mbpp"

    def _load_task(self, path: str) -> MbppTask:
        """Read the MBPP task given by ``--task-file``.

        Raises:
            OSError: the file cannot be read.
            pydantic.ValidationError: the file is not a valid MBPP task.
        """
        return MbppTask.from_file(Path(path))

    def _limits(self) -> TaskLimits:
        """Return the MBPP limits, reduced by the settings if they say so.

        Raises:
            ValueError: ``max_iterations`` of the settings is above the
                subject's limit.
        """
        return TaskLimits.mbpp(
            max_iterations=self._settings.max_iterations,
            time_margin_seconds=self._settings.time_margin_seconds,
        )
