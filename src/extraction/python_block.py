"""Extraction of Markdown Python blocks, the agent's primary format."""

import re
import textwrap

from src.extraction.base import CodeExtractor
from src.extraction.models import ExtractionResult


class PythonBlockExtractor(CodeExtractor):
    """Finds ```python ... ``` blocks in the LLM's answer.

    The model is asked to end each block with ``<end_code>``, which is
    also the stop sequence: the provider cuts the answer there, so the
    marker itself never reaches the extractor.
    """

    # One fenced block. The closing fence may be missing: the answer can
    # be cut by max_tokens, or the model may stop right after the code
    # with <end_code> and no fence, so the end of the text also closes.
    _BLOCK = re.compile(
        r"""
        ^[ \t]*```                # opening fence, at the start of a line
        [ \t]*(?P<lang>[\w+-]*)   # language tag, possibly empty
        [ \t]*\n                  # rest of the fence line
        (?P<body>.*?)             # the code: as little as possible...
        (?P<close>                # ...up to the first of:
            ^[ \t]*```[ \t]*$     #   a closing fence on its own line,
          | \Z                    #   or the end of the text
        )
        """,
        re.VERBOSE | re.DOTALL | re.MULTILINE,
    )

    _PYTHON_TAGS = ("python", "py", "python3", "")

    def extract(self, text: str) -> ExtractionResult | None:
        """Return the Python blocks of ``text``, joined in order.

        Several blocks are run as one program, in the order written: the
        sandbox keeps variables between steps anyway. Blocks are
        dedented, so an indented block does not raise IndentationError.

        Repairs, each reported in ``warnings`` for the LLM: a block
        tagged ``py``, ``python3`` or not tagged at all, a missing
        closing fence, several blocks joined.

        Returns:
            The joined code; None when there is no non-empty Python
            block, so that the other formats are tried.
        """
        blocks: list[str] = []
        warnings: list[str] = []
        for match in self._BLOCK.finditer(text):
            tag = match["lang"].lower()
            if tag not in self._PYTHON_TAGS:
                continue
            code = textwrap.dedent(match["body"]).strip("\n")
            if not code.strip():
                continue
            blocks.append(code)
            if tag == "":
                warnings.append(
                    "A code block had no language tag; it was run as "
                    "Python. Tag it ```python."
                )
            elif tag != "python":
                warnings.append(
                    f"A code block was tagged {match['lang']!r}; it was "
                    "run as Python. Tag it ```python."
                )
            if not match["close"]:
                warnings.append(
                    "A code block had no closing ```; everything after "
                    "its opening fence was run as code. Close it with "
                    "``` then write <end_code>."
                )
        if not blocks:
            return None
        if len(blocks) > 1:
            warnings.append(
                f"{len(blocks)} code blocks were found; they were joined "
                "and run in order as one. Write one block per step."
            )
        return ExtractionResult(
            code="\n\n".join(blocks),
            format_name="python",
            warnings=tuple(dict.fromkeys(warnings)),
        )
