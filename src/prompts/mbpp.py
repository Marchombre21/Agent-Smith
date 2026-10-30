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
1. Write the function and run the given tests on it.
2. If a test fails, read the error and fix the function.
3. As soon as all tests pass, call final_answer with the full source \
code as a string, imports included. A hidden test will check it too: \
keep the given signature and do not hard-code the expected results.
```python
final_answer('''import math

def area(r):
    return math.pi * r * r
''')
```<end_code>"""

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
        lines.append("Tests:")
        lines.extend(task.test_list)
        return "\n".join(lines)

    def _method(self) -> str:
        """Return the MBPP method: test, fix, answer as soon as it passes."""
        return self._METHOD
