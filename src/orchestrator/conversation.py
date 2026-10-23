"""The messages sent to the LLM, kept in order for the whole task."""

import math
from typing import List, Tuple

from src.llm.models import Message, Role


class Conversation:
    """The messages of one task, sent again to the LLM at each step.

    It starts with the system prompt and the task, then alternates the
    model's answers (``assistant``) and the observations (``user``,
    starting with ``Observation:``). Observations are not sent with the
    ``tool`` role: it needs call ids, and some providers refuse two
    messages of the same role in a row, so the order is enforced here.

    It also estimates the input tokens of the next call, so the loop can
    check the budget before calling.
    """

    # Tuned to overestimate a little: the real count is the provider's.
    _CHARS_PER_TOKEN = 3
    # Role name and separators the API adds around each message.
    _TOKENS_PER_MESSAGE = 4
    # Several APIs refuse an assistant message with no content.
    _EMPTY_ANSWER = "(empty answer)"
    _OBSERVATION_PREFIX = "Observation: "

    def __init__(self, system_prompt: str, task: str) -> None:
        """Start the conversation with the system prompt and the task.

        Args:
            system_prompt: Instructions for the model, tool manual
                included.
            task: Statement of the task, sent as the first user message.
        """
        self._messages: List[Message] = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=task),
        ]

    def add_answer(self, text: str) -> None:
        """Add the model's answer, as an ``assistant`` message.

        An empty answer is replaced by a short marker.

        Raises:
            ValueError: The last message is not a ``user`` one.
        """
        self._check_last_role("user", "an answer")
        self._messages.append(
            Message(role="assistant", content=text or self._EMPTY_ANSWER)
        )

    def add_observation(self, text: str) -> None:
        """Add an observation, as a ``user`` message.

        Args:
            text: What the sandbox run produced, already formatted;
                the ``Observation:`` prefix is added here.

        Raises:
            ValueError: The last message is not an ``assistant`` one.
        """
        self._check_last_role("assistant", "an observation")
        self._messages.append(
            Message(role="user", content=self._OBSERVATION_PREFIX + text)
        )

    @property
    def messages(self) -> Tuple[Message, ...]:
        """All the messages, system prompt first, to send to the LLM."""
        return tuple(self._messages)

    @property
    def system_prompt(self) -> str:
        """The system prompt, as given to the constructor."""
        return self._messages[0].content

    def estimate_input_tokens(self) -> int:
        """Estimate the input tokens of a call sending these messages.

        It is a rough upper estimate (characters / 3, plus a few tokens
        per message), made before the call; the provider's count, known
        after it, is the one the budget records.
        """
        return sum(
            math.ceil(len(message.content) / self._CHARS_PER_TOKEN)
            + self._TOKENS_PER_MESSAGE
            for message in self._messages
        )

    def _check_last_role(self, expected: Role, adding: str) -> None:
        """Raise if the last message does not have the expected role.

        A wrong order is a bug of the loop, not of the model.
        """
        last = self._messages[-1].role
        if last != expected:
            raise ValueError(
                f"cannot add {adding} after a {last!r} message "
                f"(expected {expected!r})"
            )
