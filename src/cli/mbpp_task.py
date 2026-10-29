"""An MBPP task: one function to write, checked by asserts."""

import json
from pathlib import Path

from src.cli.task import BenchmarkTask
from src.models import MBPPTaskInput
from src.orchestrator.models import RunResult
from src.prompts.mbpp import MbppPrompt
from src.sandbox_port import SandboxError, SandboxPort


class MbppTask(BenchmarkTask):
    """An MBPP task read from ``--task-file``.

    Wraps the input given by the moulinette (first test already hidden)
    and answers the questions of the CLI: its identifier, its prompt,
    and how to conclude.
    """

    def __init__(self, task: MBPPTaskInput) -> None:
        """Keep the input of the task.

        Args:
            task: The task as given by the moulinette.
        """
        self._task = task

    @classmethod
    def from_file(cls, path: Path) -> "MbppTask":
        """Read an MBPP task from a JSON file.

        Raises:
            OSError: the file cannot be read.
            pydantic.ValidationError: the JSON is not a valid MBPP task.
        """
        return cls(
            MBPPTaskInput.model_validate_json(path.read_text(encoding="utf-8"))
        )

    def task_id(self) -> str:
        """Return the MBPP identifier as a string, as in ``solution.json``."""
        return str(self._task.task_id)

    def prompt(self) -> MbppPrompt:
        """Return the MBPP prompt, built on this task."""
        return MbppPrompt(self._task)

    def conclude(
        self, result: RunResult, sandbox: SandboxPort
    ) -> tuple[bool, str]:
        """Take the code passed to ``final_answer`` and check it (design G).

        The first test of the task is hidden: passing the public tests
        guarantees nothing, so ``success`` only means "the agent
        believes it solved the task".

        Args:
            result: What the loop returned.
            sandbox: The sandbox of the run, still open.

        Returns:
            ``(False, "")`` without a final answer (the loop already says
            why in ``result.error``); otherwise whether the public tests
            pass, and the code. The code is kept even when they fail: the
            validation runs it anyway.
        """
        if result.final_answer is None:
            return False, ""
        solution = result.final_answer
        return self._passes_public_tests(solution, sandbox), solution

    def _passes_public_tests(
        self, solution: str, sandbox: SandboxPort
    ) -> bool:
        """Run the public tests on ``solution`` with the MCP tool
        ``run_tests``.

        ``run_tests`` starts a new process for each test, as the
        validation does, but ignores ``test_imports``: they are added
        after the solution, in the order of the validation.

        Returns:
            True only if the tool ran and reported success; False if it
            is missing (no MCP server), times out, prints something that
            is not its JSON report, or the sandbox is out of order.
        """
        code = "\n".join([solution, *self._task.test_imports])
        call = f"print(run_tests({code!r}, {self._task.test_list!r}))"
        try:
            execution = sandbox.execute(call)
        except SandboxError:
            return False
        if execution.error is not None or execution.timed_out:
            return False
        try:
            report = json.loads(execution.stdout)
        except json.JSONDecodeError:
            return False
        return isinstance(report, dict) and report.get("success") is True
