"""The interface the orchestrator uses to talk to a language model."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.llm.models import LLMResponse, Message


class LLMClient(ABC):
    """Anything that can turn a conversation into the model's next answer.

    The orchestrator depends on this class only: it never sees API keys,
    HTTP or providers. A real client (keys, retries, HTTP) and a fake one
    used for tests are both subclasses, so either can be passed to the
    agent without changing its code.
    """

    @abstractmethod
    def complete(
        self,
        messages: Sequence[Message],
        *,
        stop: Sequence[str] = (),
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> LLMResponse:
        """Send the conversation and return the model's answer.

        ``max_tokens`` and ``timeout`` are the budget left for this call,
        in tokens and in seconds: the caller passes what remains of the
        task's limits, so they are given per call and not at construction.

        Args:
            messages: The whole conversation, system prompt first.
            stop: Strings at which the model must stop generating, e.g.
                ``"<end_code>"``, so it cannot invent the observation that
                follows its code.
            max_tokens: Upper bound on generated tokens for this call;
                None leaves the provider's default.
            timeout: Seconds this call may take in total, retries and
                waits included; None means no limit.

        Raises:
            LLMError: The call failed for good (a subclass tells why).
        """
