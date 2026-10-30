"""What every benchmark prompt shares: the framework and its order."""

from abc import ABC, abstractmethod


class BenchmarkPrompt(ABC):
    """The texts that start a task: the system prompt and the task.

    The system prompt follows the shape given by the subject: a
    ``<Framework_Explanation>`` (how a step is written, the same for every
    benchmark, then the method of the benchmark) and a
    ``<Sandbox_Manual>`` (the tools, written by the sandbox from the
    connected MCP server). Subclasses fill in ``_method`` and
    ``task_message`` (template method pattern); each one receives its
    own kind of task in its constructor.
    """

    _FRAMEWORK = """\
You solve a programming task by writing Python code. The code is run \
in a sandbox, and you get back what it printed.

At each step, write:
Thought: one or two sentences on what you will do next.
```python
# your code
```<end_code>
Then stop. The Observation is written for you: never write it yourself.

Rules:
- Write code only in a ```python block ending with <end_code>. Do not \
use native tool or function calls.
- Write <end_code> only right after a code block.
- A value is not shown unless you print it: use print().
- Variables, functions and imports persist from one step to the next. \
If an Observation says variables were lost, define them again.
- Calling final_answer(...) ends the task at once.
- The functions in <Sandbox_Manual> are already defined in the sandbox: \
call them inside your ```python block, like any Python function."""

    def system_prompt(self, manual: str) -> str:
        """Build the system prompt: framework, method, then the manual.

        Args:
            manual: The sandbox manual (``SandboxPort.manual()``),
                inserted as is: the tools are never described here, so
                an unknown MCP server works the same way.
        """
        return (
            f"<Framework_Explanation>\n{self._FRAMEWORK}\n\n"
            f"{self._method()}\n</Framework_Explanation>\n\n"
            f"<Sandbox_Manual>\n{manual}\n</Sandbox_Manual>"
        )

    @abstractmethod
    def task_message(self) -> str:
        """Return the task as text: the first ``user`` message."""

    @abstractmethod
    def _method(self) -> str:
        """Return how to solve this benchmark, step by step."""
