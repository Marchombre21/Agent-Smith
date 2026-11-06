"""A SWE-bench task: an issue to fix in a real repository."""

from pathlib import Path

from src.cli.task import BenchmarkTask
from src.models import SWEBenchTaskInput
from src.orchestrator.models import RunResult
from src.prompts.swebench import SweBenchPrompt
from src.sandbox_port import SandboxPort


class SweBenchTask(BenchmarkTask):
    """A SWE-bench task read from ``--task-file``.

    Wraps the input given by the moulinette (issue, Docker image,
    evaluation script) and answers the questions of the CLI: its
    identifier, its prompt, and how to conclude.
    """

    # First line of a diff written by git; the moulinette rejects a
    # solution that does not look like a patch.
    _DIFF_START = "diff --git "

    def __init__(self, task: SWEBenchTaskInput) -> None:
        """Keep the input of the task.

        Args:
            task: The task as given by the moulinette.
        """
        self._task = task

    @classmethod
    def from_file(cls, path: Path) -> "SweBenchTask":
        """Read a SWE-bench task from a JSON file.

        Raises:
            OSError: the file cannot be read.
            pydantic.ValidationError: the JSON is not a valid SWE-bench
                task.
        """
        return cls(
            SWEBenchTaskInput.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        )

    def task_id(self) -> str:
        """Return the instance id (``sympy__sympy-13480``), as in
        ``solution.json``."""
        return self._task.instance_id

    def prompt(self) -> SweBenchPrompt:
        """Return the SWE-bench prompt, built on this task."""
        return SweBenchPrompt(self._task)

    def setup_code(self) -> str:
        """Return nothing to run: the tools are all the model needs.

        The repository lives in the container, not in the sandbox, so
        there is no data to define in advance as MBPP does with its
        tests.
        """
        return ""

    def conclude(
        self, result: RunResult, sandbox: SandboxPort, timeout: float
    ) -> tuple[bool, str]:
        """Take the patch passed to ``final_answer`` (subject, V.2).

        The subject's mechanism: the model calls
        ``final_answer(get_patch())`` and its argument is the solution.
        Nothing is rebuilt when it is missing, as for MBPP (unit 56
        rejected): a run without ``final_answer`` failed, and the report
        measures when the model submits.

        Args:
            result: What the loop returned.
            sandbox: Not used: the patch was computed by the model's own
                call to ``get_patch``.
            timeout: Not used, nothing is run.

        Returns:
            ``(False, "")`` without a final answer (the loop already says
            why in ``result.error``) or when it is not a diff, for
            instance the sentence ``get_patch`` returns when nothing was
            changed; otherwise ``(True, patch)``.
        """
        answer = result.final_answer
        if answer is None or not answer.startswith(self._DIFF_START):
            return False, ""
        return True, answer
