"""The LLM client given to the orchestrator: retries and key rotation."""

import logging
import math
import time
from collections.abc import Callable, Sequence

from src.llm.chat_api import ChatCompletionsApi
from src.llm.client import LLMClient
from src.llm.config import ApiKey
from src.llm.errors import AuthError, LLMError, ProviderError, RateLimitError
from src.llm.key_pool import KeyPool
from src.llm.models import LLMResponse, Message


class RotatingClient(LLMClient):
    """Calls one provider, rotating keys and retrying until success or limit.

    Each ``complete()`` makes attempts through ``ChatCompletionsApi`` with
    the key handed out by ``KeyPool``, and reacts to each failure by its
    type: next key on a rate limit or a refused key, short wait on a
    provider failure, immediate stop on a bad request. It always stops,
    after ``max_attempts`` attempts or when the call's ``timeout`` runs
    out, and then raises the last error.

    The ``clock`` and ``sleep`` functions are injected so that tests can
    simulate long waits instantly.
    """

    _log = logging.getLogger(__name__)
    # Block applied to a rate-limited key when the provider gives no
    # Retry-After: free tiers mostly count their limits per minute.
    _DEFAULT_RATE_LIMIT_WAIT = 60.0
    # Backoff after a provider failure: 1, 2, 4, then 8 s at most.
    _BACKOFF_BASE = 1.0
    _BACKOFF_MAX = 8.0

    def __init__(
        self,
        api: ChatCompletionsApi,
        pool: KeyPool,
        *,
        max_attempts: int = 6,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Combine an API (one provider, one model) with its key pool.

        Args:
            api: Makes single HTTP attempts.
            pool: The keys of the same provider.
            max_attempts: Attempts per ``complete()`` call, the first one
                included.
            clock: Returns seconds; only differences are used. It must be
                the clock ``pool`` uses, so that blocks and waits agree.
            sleep: Waits the given number of seconds.

        Raises:
            ValueError: ``max_attempts`` is lower than 1.
        """
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._api = api
        self._pool = pool
        self._max_attempts = max_attempts
        self._clock = clock
        self._sleep = sleep

    def complete(
        self,
        messages: Sequence[Message],
        *,
        stop: Sequence[str] = (),
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> LLMResponse:
        """Get the model's answer, retrying and rotating keys as needed.

        The returned ``LLMResponse`` counts the failed attempts in
        ``retries``, and its ``request_time_ms`` covers the whole call,
        failed attempts and waits included.

        Raises:
            ValueError: ``timeout`` is zero or negative.
            LLMError: The last error, when attempts or time ran out or the
                request itself was refused; a ``RateLimitError`` when
                every key stayed blocked and no attempt could be made.
        """
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be positive")
        start = self._clock()
        end = math.inf if timeout is None else start + timeout
        last_error: LLMError | None = None
        for attempt in range(1, self._max_attempts + 1):
            key = self._pool.acquire()
            if key is None:
                wait = self._pool.wait_time()
                if self._clock() + wait >= end or math.isinf(wait):
                    break
                self._sleep(wait)
                key = self._pool.acquire()
                if key is None:
                    break
            remaining = end - self._clock()
            if remaining <= 0:
                break
            try:
                response = self._api.send(
                    key,
                    messages,
                    stop=stop,
                    max_tokens=max_tokens,
                    timeout=None if math.isinf(remaining) else remaining,
                )
            except LLMError as error:
                last_error = error
                delay = self._react(error, key, attempt)
                if delay > 0 and attempt < self._max_attempts:
                    if self._clock() + delay >= end:
                        break
                    self._sleep(delay)
                continue
            return response.model_copy(
                update={
                    "retries": attempt - 1,
                    "request_time_ms": (self._clock() - start) * 1000,
                }
            )
        if last_error is not None:
            raise last_error
        raise RateLimitError(
            "every key is blocked and none is released in time",
            self._pool.wait_time(),
        )

    def _react(self, error: LLMError, key: ApiKey, attempt: int) -> float:
        """Apply the reaction to a failed attempt; return the wait before
        the next attempt.

        - rate limit: block ``key`` for the advised delay (60 s if none),
          then try the next key at once;
        - refused key: block ``key`` for good, then try the next key;
        - provider failure: same key, after a backoff of 1, 2, 4, 8 s...;
        - anything else (bad request): retrying cannot help, re-raise.

        Args:
            error: What the attempt raised.
            key: The key that attempt used.
            attempt: Number of that attempt, starting at 1.

        Returns:
            Seconds to wait before the next attempt (0.0 for none).

        Raises:
            LLMError: ``error`` itself, when it is not worth retrying.
        """
        self._log.warning(
            "attempt %d with %s failed: %s", attempt, key.env_name, error
        )
        if isinstance(error, RateLimitError):
            delay = error.retry_after
            if delay is None:
                delay = self._DEFAULT_RATE_LIMIT_WAIT
            self._pool.block(key, delay)
            return 0.0
        if isinstance(error, AuthError):
            self._pool.block(key, math.inf)
            return 0.0
        if isinstance(error, ProviderError):
            backoff = self._BACKOFF_BASE * 2.0 ** (attempt - 1)
            return min(backoff, self._BACKOFF_MAX)
        raise error
