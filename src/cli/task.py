"""A task of a benchmark: its data, and what to do with it."""

from abc import ABC, abstractmethod

from src.orchestrator.models import RunResult
from src.prompts.base import BenchmarkPrompt
from src.sandbox_port import SandboxPort


class BenchmarkTask(ABC):
    """One task read from ``--task-file``, as the CLI sees it.

    Each benchmark wraps its own input model (``MBPPTaskInput``,
    ``SWEBenchTaskInput``) in a subclass that knows how to present the
    task to the LLM and how to turn the end of the loop into a solution.
    The CLI only uses this interface, whatever the benchmark.
    """

    @abstractmethod
    def task_id(self) -> str:
        """Return the identifier of the task, as in ``solution.json``."""

    @abstractmethod
    def prompt(self) -> BenchmarkPrompt:
        """Return the prompt that starts the task."""

    @abstractmethod
    def conclude(
        self, result: RunResult, sandbox: SandboxPort
    ) -> tuple[bool, str]:
        """Turn the end of the loop into ``(success, solution)``.

        Called while the sandbox is still open: MBPP runs the public
        tests in it, SWE-bench computes the patch in the container.

        Args:
            result: What the loop returned: the value passed to
                ``final_answer``, or why it stopped without one.
            sandbox: The sandbox of the run, still open.

        Returns:
            Whether the agent believes it solved the task, and the
            solution to write (MBPP code, SWE-bench patch); the solution
            may be empty when the task failed.
        """
