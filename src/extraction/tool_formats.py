"""Extraction of tool calls written in non-Python formats."""

import json
import re
from typing import Any

from pydantic import ValidationError

from src.extraction.base import CodeExtractor, ExtractionResult
from src.extraction.tool_call import ToolCall


class HermesExtractor(CodeExtractor):
    """Finds ``<tool_call>{"name": ..., "arguments": {...}}</tool_call>``.

    A convention from the Hermes models, also used by Qwen: no formal
    standard, so common variants are tolerated (see ``extract``).
    """

    # One call. </tool_call> is usually missing: the orchestrator puts it
    # in the stop sequences, so the provider cuts it off like <end_code>.
    # Without it, the call ends at the next <tool_call> or at the end.
    _TOOL_CALL = re.compile(
        r"""
        <tool_call>
        (?P<body>.*?)            # the JSON, as little as possible...
        (?:                      # ...up to the first of:
            </tool_call>         #   the closing tag,
          | (?=<tool_call>)      #   the next call (not consumed),
          | \Z                   #   or the end of the text
        )
        """,
        re.VERBOSE | re.DOTALL,
    )

    @staticmethod
    def _parse(body: str) -> tuple[ToolCall, list[str]]:
        """Turn the JSON between the tags into a ``ToolCall``.

        Tolerated variants, each reported by a warning: ``"arguments"``
        missing or null (no argument), or given as a JSON string, as the
        OpenAI API does.

        Returns:
            The call, and the warnings for the LLM.

        Raises:
            ValueError: the body cannot be used; the message says why
                and is meant for the LLM.
        """

        def reject(constant: str) -> Any:
            raise ValueError(f"{constant} is not valid JSON")

        try:
            data = json.loads(body, parse_constant=reject)
        except ValueError as error:
            raise ValueError(f"invalid JSON in <tool_call>: {error}") from None
        if not isinstance(data, dict):
            raise ValueError("<tool_call> must contain a JSON object")
        name = data.get("name")
        if not isinstance(name, str):
            raise ValueError('<tool_call> needs a "name" string')

        warnings: list[str] = []
        arguments = data.get("arguments")
        if arguments is None:
            arguments = {}
            warnings.append(
                f'The <tool_call> to {name} had no "arguments"; it was '
                "called without any."
            )
        elif isinstance(arguments, str):
            try:
                arguments = json.loads(arguments, parse_constant=reject)
            except ValueError as error:
                raise ValueError(
                    f'"arguments" of {name} is a string, not JSON: {error}'
                ) from None
            warnings.append(
                f'"arguments" of {name} was a JSON string; it was decoded. '
                "Give a JSON object instead."
            )
        if not isinstance(arguments, dict):
            raise ValueError(f'"arguments" of {name} must be a JSON object')

        try:
            return ToolCall(name=name, arguments=arguments), warnings
        except ValidationError as error:
            causes = "; ".join(
                detail["msg"].removeprefix("Value error, ")
                for detail in error.errors()
            )
            raise ValueError(causes) from None

    def extract(self, text: str) -> ExtractionResult | None:
        """Convert the ``<tool_call>`` blocks of ``text`` into Python.

        Several calls are run in order, as one program. If any of them
        cannot be used, none is run: half of a sequence of edits would
        leave the repository in a state the model did not intend.

        Returns:
            None when there is no ``<tool_call>``, so that the other
            formats are tried; otherwise a result whose code is None
            when a call is broken, with the cause in ``warnings``.
        """
        bodies = [match["body"] for match in self._TOOL_CALL.finditer(text)]
        if not bodies:
            return None

        calls: list[ToolCall] = []
        warnings: list[str] = []
        for number, body in enumerate(bodies, start=1):
            try:
                call, call_warnings = self._parse(body)
            except ValueError as error:
                where = (
                    f"<tool_call> {number} of {len(bodies)}"
                    if len(bodies) > 1
                    else "<tool_call>"
                )
                return ExtractionResult(
                    code=None,
                    format_name="hermes",
                    warnings=(f"Nothing was run. {where}: {error}",),
                )
            calls.append(call)
            warnings.extend(call_warnings)

        if len(calls) > 1:
            warnings.append(
                f"{len(calls)} tool calls were found; they were run in "
                "order as one program."
            )
        return ExtractionResult(
            code="\n".join(call.to_python() for call in calls),
            format_name="hermes",
            warnings=tuple(dict.fromkeys(warnings)),
        )
