"""A tool call written in a non-Python format, before its conversion."""

import keyword
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class ToolCall(BaseModel):
    """One call to a sandbox tool, as parsed from XML, JSON or ReAct.

    The three non-Python formats all boil down to a tool name and named
    arguments; this class is what they have in common, so the conversion
    to Python is written once.

    The name and argument names end up verbatim in the generated code,
    so they must be plain Python identifiers: a name such as
    ``"x; import os"`` would otherwise inject code. Argument values are
    safe, since they are written with ``repr``.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    arguments: dict[str, Any]

    @staticmethod
    def _check_identifier(value: str, what: str) -> str:
        """Return ``value`` if it can be written as-is in Python code.

        Raises:
            ValueError: ``value`` is not an identifier, or is a keyword.
        """
        if not value.isidentifier() or keyword.iskeyword(value):
            raise ValueError(f"{what} {value!r} is not a Python identifier")
        return value

    @field_validator("name")
    @classmethod
    def _valid_name(cls, value: str) -> str:
        """Reject a tool name that is not a Python identifier."""
        return cls._check_identifier(value, "tool name")

    @field_validator("arguments")
    @classmethod
    def _valid_argument_names(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Reject an argument name that is not a Python identifier."""
        for name in value:
            cls._check_identifier(name, "argument name")
        return value

    def to_python(self) -> str:
        """Write the call as Python code for the sandbox.

        The result is stored in ``result`` and printed, so that it shows
        up in the observation; the variable stays available to the next
        steps like any other.

        Example: ``read_file(filepath="/testbed/a.py")`` becomes::

            result = read_file(filepath='/testbed/a.py')
            print(result)
        """
        args = ", ".join(
            f"{name}={value!r}" for name, value in self.arguments.items()
        )
        return f"result = {self.name}({args})\nprint(result)"
