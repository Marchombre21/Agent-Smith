"""The messages sent to the LLM, kept in order for the whole task."""

import math
from typing import List, Optional, Tuple

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

    Each call sends every message again, so an old observation costs its
    size once per later step. To save input tokens, only the last
    observations can be sent in full, the older ones being replaced by a
    short marker. The full text is kept here: only the view sent changes.
    """

    # Tuned to overestimate a little: the real count is the provider's.
    _CHARS_PER_TOKEN = 3
    # Role name and separators the API adds around each message.
    _TOKENS_PER_MESSAGE = 4
    # Several APIs refuse an assistant message with no content.
    _EMPTY_ANSWER = "(empty answer)"
    _OBSERVATION_PREFIX = "Observation: "
    # The variables survive in the sandbox: printing one again is cheaper
    # than calling the tool that produced it.
    _REMOVED_OBSERVATION = (
        "[Output of an earlier step removed to save tokens "
        "({length} characters). Your variables still exist in the "
        "sandbox: print them again if needed.]"
    )
    # System prompt and task: the messages before the first answer.
    _OPENING_MESSAGES = 2

    def __init__(
        self,
        system_prompt: str,
        task: str,
        keep_last_observations: Optional[int] = None,
    ) -> None:
        """Start the conversation with the system prompt and the task.

        Args:
            system_prompt: Instructions for the model, tool manual
                included.
            task: Statement of the task, sent as the first user message.
            keep_last_observations: How many of the latest observations
                are sent in full; older ones are replaced by a marker.
                None sends them all in full.

        Raises:
            ValueError: ``keep_last_observations`` is negative.
        """
        if keep_last_observations is not None and keep_last_observations < 0:
            raise ValueError(
                f"keep_last_observations={keep_last_observations} "
                f"must be 0 or more"
            )
        self._keep_last_observations = keep_last_observations
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
        """The messages to send to the LLM, system prompt first.

        Observations older than the last ``keep_last_observations`` are
        replaced by a marker giving their length, unless the marker would
        be longer than the observation itself.
        """
        kept_in_full = self._keep_last_observations
        if kept_in_full is None:
            return tuple(self._messages)
        observation_positions = [
            index
            for index, message in enumerate(self._messages)
            if index >= self._OPENING_MESSAGES and message.role == "user"
        ]
        old_count = max(0, len(observation_positions) - kept_in_full)
        old_positions = set(observation_positions[:old_count])
        return tuple(
            self._shortened(message) if position in old_positions else message
            for position, message in enumerate(self._messages)
        )

    def estimate_input_tokens(self) -> int:
        """Estimate the input tokens of a call sending these messages.

        It is a rough upper estimate (characters / 3, plus a few tokens
        per message), made before the call; the provider's count, known
        after it, is the one the budget records.
        """
        return sum(
            math.ceil(len(message.content) / self._CHARS_PER_TOKEN)
            + self._TOKENS_PER_MESSAGE
            for message in self.messages
        )

    def _shortened(self, observation: Message) -> Message:
        """Return the marker standing for an old observation.

        A short observation (``(no output)``) is returned unchanged: the
        marker would cost more than it.
        """
        length = len(observation.content) - len(self._OBSERVATION_PREFIX)
        marker = self._OBSERVATION_PREFIX + self._REMOVED_OBSERVATION.format(
            length=length
        )
        if len(marker) >= len(observation.content):
            return observation
        return Message(role="user", content=marker)

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
