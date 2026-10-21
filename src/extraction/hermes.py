"""Extraction of Hermes tool calls: <tool_call>{json}</tool_call>."""

import json
import re

from src.extraction.tool_call import ToolCall
from src.extraction.tool_call_extractor import ToolCallExtractor


class HermesExtractor(ToolCallExtractor):
    """Finds ``<tool_call>{"name": ..., "arguments": {...}}</tool_call>``.

    A convention from the Hermes models, also used by Qwen: no formal
    standard, so common variants are tolerated (see ``_parse``).
    """

    _FORMAT = "hermes"
    _LABEL = "<tool_call>"

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

    def _find(self, text: str) -> list[str]:
        """Return the JSON text of each ``<tool_call>``."""
        return [match["body"] for match in self._TOOL_CALL.finditer(text)]

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

        try:
            data = json.loads(
                body, parse_constant=ToolCallExtractor._reject_constant
            )
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
                arguments = json.loads(
                    arguments,
                    parse_constant=ToolCallExtractor._reject_constant,
                )
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

        return ToolCallExtractor._build_call(name, arguments), warnings
