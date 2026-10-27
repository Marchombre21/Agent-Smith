"""The prompt of a SWE-bench task: fix an issue in a real repository."""

from src.models import SWEBenchTaskInput
from src.prompts.base import BenchmarkPrompt


class SweBenchPrompt(BenchmarkPrompt):
    """Prompt for a SWE-bench task: explore, fix, test, give the patch.

    The tools named here are the mandatory ones of the subject; how to
    call them is in the sandbox manual, not here.
    """

    _METHOD = """\
Method:
1. Find the code involved in the issue with search_code and \
search_function_or_class_definition_in_code. Keep long outputs in \
variables and print only the part you need.
2. Read the relevant lines with read_file and line numbers, not whole \
files.
3. If you can, reproduce the bug with a short script (run_command) \
before changing anything.
4. Fix the source code with edit_file. Change as little as needed and \
do not edit the tests.
5. Call run_tests() and read which tests fail. Fix, then run them again.
6. When the tests pass, call final_answer(get_patch()).
Work only from the repository and the tools: never look for the fix \
in a pull request, an issue or any other outside source.

Example:
Thought: I look for the function named in the issue.
```python
hits = search_function_or_class_definition_in_code("parse_date")
print(hits)
```<end_code>
Observation: /testbed/pkg/dates.py:42 def parse_date(text):
Thought: I read this function.
```python
print(read_file("/testbed/pkg/dates.py", 42, 60))
```<end_code>
Observation: 42: def parse_date(text):
...
47:     return datetime.strptime(text, "%d/%m/%y")
Thought: The year needs 4 digits: %Y, not %y. I fix it and run the tests.
```python
print(edit_file("/testbed/pkg/dates.py", '"%d/%m/%y"', '"%d/%m/%Y"'))
print(run_tests())
```<end_code>
Observation: ... all tests passed
Thought: The tests pass.
```python
final_answer(get_patch())
```<end_code>"""

    def __init__(self, task: SWEBenchTaskInput) -> None:
        """Keep the task to write into the first message.

        Args:
            task: The task as given by the moulinette.
        """
        self._task = task

    def task_message(self) -> str:
        """Return the repository, the issue and the hints if any.

        The evaluation script is left out: it can be long, this message
        is sent again at every step, and ``run_tests()`` runs it anyway.
        """
        task = self._task
        lines = [
            f"Repository: {task.repo or task.instance_id}, in /testbed.",
            "Issue:",
            task.problem_statement,
        ]
        if task.hints_text:
            lines.extend(["Hints:", task.hints_text])
        return "\n".join(lines)

    def _method(self) -> str:
        """Return the SWE-bench method: locate, read, fix, test, patch."""
        return self._METHOD
