"""Extraction of Anthropic-style XML tool calls: <invoke>."""

import json
import re
from typing import Any

from src.extraction.tool_call import ToolCall
from src.extraction.tool_call_extractor import ToolCallExtractor


class XmlExtractor(ToolCallExtractor):
    """Finds Anthropic-style ``<invoke name="..."><parameter name="...">``.

    Values are raw text, not JSON: code is written as is, with its line
    breaks and without escaping. The ``<function_calls>`` wrapper that
    often surrounds the calls is not needed and is ignored.
    """

    _FORMAT = "xml"
    _LABEL = "<invoke>"

    # One call, from <invoke ...> to </invoke>; the closing tag may be
    # missing (stop sequence), like </tool_call> for Hermes. The name is
    # optional here so that a call without one is reported, not skipped.
    _INVOKE = re.compile(
        r"""
        <invoke\b
        (?:\s+name\s*=\s*["'](?P<name>[^"']*)["'])?   # name="..."
        \s*>
        (?P<body>.*?)            # the parameters, as little as possible...
        (?:                      # ...up to the first of:
            </invoke>            #   the closing tag,
          | (?=<invoke\b)        #   the next call (not consumed),
          | \Z                   #   or the end of the text
        )
        """,
        re.VERBOSE | re.DOTALL,
    )
    # One parameter. Its closing tag is required: without it, the value
    # was cut off and must not reach the sandbox.
    _PARAMETER = re.compile(
        r"""
        <parameter\s+name\s*=\s*["'](?P<name>[^"']*)["']\s*>
        (?P<value>.*?)
        </parameter>
        """,
        re.VERBOSE | re.DOTALL,
    )

    def _find(self, text: str) -> list[str]:
        """Return the full text of each ``<invoke>``, tags included.

        ``_parse`` matches ``_INVOKE`` again on it to read the name.
        """
        return [match[0] for match in self._INVOKE.finditer(text)]

    @staticmethod
    def _value(text: str) -> Any:
        """Turn the raw text of a ``<parameter>`` into a Python value.

        One line break is removed on each side, since models put the
        tags on their own lines; spaces are kept, as the indentation of
        code matters (``edit_file`` looks for an exact string). Text that
        is JSON other than a string (a number, true/false/null, a list,
        an object) is decoded: ``test_list`` must arrive as a list.
        Anything else stays text, quotes included.
        """

        text = text.removeprefix("\n").removesuffix("\n")
        try:
            decoded = json.loads(
                text, parse_constant=ToolCallExtractor._reject_constant
            )
        except ValueError:
            return text
        return text if isinstance(decoded, str) else decoded

    def _parse(self, body: str) -> tuple[ToolCall, list[str]]:
        """Read the name and parameters of one ``<invoke>``.

        Args:
            body: The whole text of the call, as returned by ``_find``.

        Returns:
            The call, and no warning: nothing is repaired here.

        Raises:
            ValueError: the name is missing, a ``<parameter>`` is not
                closed (its value may be cut off) or appears twice, or
                a name is not a Python identifier.
        """
        match = self._INVOKE.match(body)
        if match is None or not match["name"]:
            raise ValueError('<invoke> needs a name="..." attribute')
        name = match["name"]
        parameters = list(self._PARAMETER.finditer(match["body"]))
        if match["body"].count("<parameter") > len(parameters):
            raise ValueError(
                f"a <parameter> of {name} has no </parameter>; its value "
                "may be cut off"
            )

        arguments: dict[str, Any] = {}
        for parameter in parameters:
            if parameter["name"] in arguments:
                raise ValueError(
                    f'parameter "{parameter["name"]}" of {name} is given '
                    "twice"
                )
            arguments[parameter["name"]] = self._value(parameter["value"])

        return self._build_call(name, arguments), []
