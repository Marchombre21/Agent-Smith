"""A task of a benchmark: its data, and what to do with it."""

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager

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
    def setup_code(self) -> str:
        """Return the code to run in the sandbox before the first step.

        It defines what the model may use without writing it (MBPP: the
        given tests). The loop runs it again whenever the sandbox loses
        its variables. An empty string means nothing to run.
        """

    @abstractmethod
    def mcp_environment(self) -> AbstractContextManager[dict[str, str]]:
        """Prepare what the MCP server needs, for the whole run.

        Used as ``with task.mcp_environment() as env:``. Entering
        prepares the outside world the tools work on (SWE-bench: the
        Docker container and the evaluation script) and gives the
        environment variables that tell the MCP server where it is;
        leaving removes it all, even on an error or SIGTERM. The server
        reads the variables when it starts, so the sandbox must be
        opened inside the block.

        Implementations are usually generators decorated with
        ``contextlib.contextmanager``.
        """

    @abstractmethod
    def conclude(
        self, result: RunResult, sandbox: SandboxPort, timeout: float
    ) -> tuple[bool, str]:
        """Turn the end of the loop into ``(success, solution)``.

        Called while the sandbox is still open: MBPP runs the public
        tests in it, SWE-bench computes the patch in the container.

        Args:
            result: What the loop returned: the value passed to
                ``final_answer``, or why it stopped without one.
            sandbox: The sandbox of the run, still open.
            timeout: Seconds left before the task's deadline; zero or
                less when the loop used it all. Work done here counts
                towards the subject's time limit too.

        Returns:
            Whether the agent believes it solved the task, and the
            solution to write (MBPP code, SWE-bench patch); the solution
            may be empty when the task failed.
        """
