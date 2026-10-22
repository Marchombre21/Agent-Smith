"""Extraction of ReAct actions: Action: tool / Action Input: {json}."""

import json
import re

from src.extraction.tool_call import ToolCall
from src.extraction.tool_call_extractor import ToolCallExtractor


class ReActExtractor(ToolCallExtractor):
    """Finds ``Action: tool_name`` followed by ``Action Input: {...}``.

    ReAct is a prompting convention, not a trained format: it is the
    loosest of all, so ``Action:`` must start a line to count. The
    ``Final Answer:`` line of ReAct is not handled here.
    """

    _FORMAT = "react"
    _LABEL = "Action"

    # One action: the tool name on the Action: line, then everything up
    # to the next Action: line or the end. "Action Input:" does not end
    # it: after "Action" comes " Input", not ":".
    _ACTION = re.compile(
        r"""
        ^[ \t]*Action[ \t]*:[ \t]*
        (?P<name>[^\n]*)          # the rest of the line: the tool name
        (?P<rest>.*?)             # Action Input and what follows...
        (?=                       # ...up to, without consuming it:
            ^[ \t]*Action[ \t]*:  #   the next Action: line,
          | \Z                    #   or the end of the text
        )
        """,
        re.VERBOSE | re.DOTALL | re.MULTILINE,
    )
    # The line that introduces the arguments, inside one action.
    _INPUT = re.compile(r"^[ \t]*Action[ \t]+Input[ \t]*:", re.MULTILINE)

    def _find(self, text: str) -> list[str]:
        """Return the full text of each action, ``Action:`` line included.

        ``_parse`` matches ``_ACTION`` again on it to read the name.
        """
        return [match[0] for match in self._ACTION.finditer(text)]

    def _parse(self, body: str) -> tuple[ToolCall, list[str]]:
        """Read the tool name and the JSON object of one action.

        Only the first JSON value after ``Action Input:`` is read, on
        one line or several; what follows it (an ``Observation:`` the
        model made up, more text) is ignored. A missing ``Action
        Input:`` means no argument, with a warning.

        Args:
            body: The whole text of the action, as returned by ``_find``.

        Raises:
            ValueError: the name is empty, or the input is not a JSON
                object, or a name is not a Python identifier.
        """
        match = self._ACTION.match(body)
        name = match["name"].strip() if match else ""
        if not name or match is None:
            raise ValueError("Action: needs a tool name")

        found = self._INPUT.search(match["rest"])
        if found is None:
            return self._build_call(name, {}), [
                f"The Action {name} had no Action Input; it was called "
                "without any."
            ]
        text = match["rest"][found.end():].lstrip()
        decoder = json.JSONDecoder(parse_constant=self._reject_constant)
        try:
            arguments, _ = decoder.raw_decode(text)
        except ValueError as error:
            raise ValueError(
                f"Action Input of {name} is not valid JSON ({error}); "
                'give a JSON object, e.g. {"filepath": "a.py"}'
            ) from None
        if not isinstance(arguments, dict):
            raise ValueError(
                f"Action Input of {name} must be a JSON object, "
                'e.g. {"filepath": "a.py"}'
            )
        return self._build_call(name, arguments), []
