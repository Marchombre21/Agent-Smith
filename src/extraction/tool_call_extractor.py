"""Common algorithm of the extractors that read tool calls."""

from abc import abstractmethod
from typing import Any

from pydantic import ValidationError

from src.extraction.base import CodeExtractor
from src.extraction.models import ExtractionResult
from src.extraction.tool_call import ToolCall


class ToolCallExtractor(CodeExtractor):
    """Common algorithm of the formats that describe tool calls.

    XML, Hermes and ReAct differ only in how calls are found in the text
    and how one call is read; what to do with the calls is the same and
    is written once, in ``extract``. Subclasses fill in ``_find``,
    ``_parse``, ``_FORMAT`` and ``_LABEL`` (template method pattern).
    """

    _FORMAT: str  # ExtractionResult.format_name, e.g. "hermes"
    _LABEL: str  # How a call is named to the LLM, e.g. "<tool_call>"

    @staticmethod
    def _reject_constant(constant: str) -> Any:
        """Refuse NaN and Infinity, for ``json.loads(parse_constant=...)``.

        json.loads accepts them although they are not JSON; they would
        become the undefined names nan and inf in the generated code.
        """
        raise ValueError(f"{constant} is not valid JSON")

    @staticmethod
    def _build_call(name: str, arguments: dict[str, Any]) -> ToolCall:
        """Build the ``ToolCall``, with a short cause if it is refused.

        Raises:
            ValueError: a name is not a Python identifier; the message
                is pydantic's cause alone, without its header.
        """
        try:
            return ToolCall(name=name, arguments=arguments)
        except ValidationError as error:
            causes = "; ".join(
                detail["msg"].removeprefix("Value error, ")
                for detail in error.errors()
            )
            raise ValueError(causes) from None

    @abstractmethod
    def _find(self, text: str) -> list[str]:
        """Return the text of each call found in ``text``, in order."""

    @abstractmethod
    def _parse(self, body: str) -> tuple[ToolCall, list[str]]:
        """Read one call; return it with the warnings for the LLM.

        Raises:
            ValueError: the call cannot be used; the message says why
                and is meant for the LLM.
        """

    def extract(self, text: str) -> ExtractionResult | None:
        """Convert the tool calls of ``text`` into Python.

        Several calls are run in order, as one program. If any of them
        cannot be used, none is run: half of a sequence of edits would
        leave the repository in a state the model did not intend.

        Returns:
            None when the format is absent, so that the other formats
            are tried; otherwise a result whose code is None when a call
            is broken, with the cause in ``warnings``.
        """
        bodies = self._find(text)
        if not bodies:
            return None

        calls: list[ToolCall] = []
        warnings: list[str] = []
        for number, body in enumerate(bodies, start=1):
            try:
                call, call_warnings = self._parse(body)
            except ValueError as error:
                where = (
                    f"{self._LABEL} {number} of {len(bodies)}"
                    if len(bodies) > 1
                    else self._LABEL
                )
                return ExtractionResult(
                    code=None,
                    format_name=self._FORMAT,
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
            format_name=self._FORMAT,
            warnings=tuple(dict.fromkeys(warnings)),
        )
