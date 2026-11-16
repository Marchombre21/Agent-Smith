"""The command line of the SWE-bench agent (``python -m agent_swebench``)."""

from pathlib import Path
from typing import Literal

from src.cli.base import BenchmarkCli
from src.cli.swebench_task import SweBenchTask
from src.orchestrator.models import TaskLimits


class SweBenchCli(BenchmarkCli):
    """Solve one SWE-bench task: everything else comes from
    ``BenchmarkCli``."""

    def _benchmark(self) -> Literal["mbpp", "swebench"]:
        """Return ``"swebench"``."""
        return "swebench"

    def _load_task(self, path: str) -> SweBenchTask:
        """Read the SWE-bench task given by ``--task-file``.

        Raises:
            OSError: the file cannot be read.
            pydantic.ValidationError: the file is not a valid SWE-bench
                task.
        """
        return SweBenchTask.from_file(Path(path))

    def _limits(self) -> TaskLimits:
        """Return the SWE-bench limits, reduced by the settings if they
        say so.

        Raises:
            ValueError: ``max_iterations`` of the settings is above the
                subject's limit.
        """
        return TaskLimits.swebench(
            max_iterations=self._settings.max_iterations,
            time_margin_seconds=self._settings.time_margin_seconds,
            max_output_tokens_per_call=(
                self._settings.max_output_tokens_per_call
            ),
        )
