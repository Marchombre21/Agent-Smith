"""The prompt of an MBPP task: write one Python function."""

from src.models import MBPPTaskInput
from src.prompts.base import BenchmarkPrompt


class MbppPrompt(BenchmarkPrompt):
    """Prompt for an MBPP task: one function, checked by asserts.

    Kept as short as possible: the system prompt is sent again at every
    step, and MBPP allows only 6,000 input tokens for the whole task.
    """

    _METHOD = """\
Method:
Before your first step, the sandbox defines TESTS, the list of the \
given tests.
1. Put the full source of the function, imports included, in a string \
named code, and in the same code block check it with \
print(run_tests(code, TESTS)), like this:
```python
code = '''import math

def area(r):
    return math.pi * r * r
'''
print(run_tests(code, TESTS))
```<end_code>
2. If a test fails, read the error and fix code.
3. Once an Observation shows that all tests pass, call final_answer(code) \
in a new step. A hidden test will check it too: keep the given \
signature and do not hard-code the expected results."""

    def __init__(self, task: MBPPTaskInput) -> None:
        """Keep the task to write into the first message.

        Args:
            task: The task as given by the moulinette, first test
                already hidden.
        """
        self._task = task

    def task_message(self) -> str:
        """Return the description, the signature and the given tests."""
        task = self._task
        lines = [
            task.task_definition,
            f"Signature: {task.function_definition}",
        ]
        if task.test_imports:
            lines.append("Test imports:")
            lines.extend(task.test_imports)
        # TESTS is defined in the sandbox by MbppTask.setup_code.
        lines.append("Tests (already in the list TESTS):")
        lines.extend(task.test_list)
        return "\n".join(lines)

    def _method(self) -> str:
        """Return the MBPP method: check with run_tests, fix, answer."""
        return self._METHOD
