"""Errors raised by the LLM layer, one class per reaction expected.

The HTTP client turns every failure into one of these types; the retry
policy then picks its reaction from the type alone, without looking at
status codes again.
"""


class LLMError(Exception):
    """Base class of every failure of an LLM call.

    Catching ``LLMError`` catches all the errors below, and nothing else
    (``KeyboardInterrupt`` and ``SystemExit`` are not ``Exception``).
    """


class RateLimitError(LLMError):
    """The key hit a rate limit or its quota (HTTP 429).

    Reaction: set this key aside for ``retry_after`` seconds and move on
    to the next key.
    """

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        """Store the delay advised by the provider, if it gave one.

        Args:
            message: Human-readable description, for the logs.
            retry_after: Seconds to wait before using this key again, read
                from the ``Retry-After`` header; None when absent.
        """
        super().__init__(message)
        self._retry_after = retry_after

    @property
    def retry_after(self) -> float | None:
        """Seconds advised by the provider before retrying, or None."""
        return self._retry_after


class AuthError(LLMError):
    """The key was refused (HTTP 401 or 403): wrong, revoked or expired.

    Reaction: retrying with the same key is pointless; set it aside for a
    long time and move on to the next key.
    """


class ProviderError(LLMError):
    """The provider failed on its side (5xx, timeout, network, bad JSON).

    Reaction: the request itself is fine, so wait a little (backoff) and
    try again.
    """


class NativeToolCallError(ProviderError):
    """The model attempted a native tool call and returned no text.

    The prompt asks for tools to be called from Python code, but some
    models call them through the API anyway: Gemini filters the call
    (``finish_reason`` ``MALFORMED_FUNCTION_CALL``) and often sends back
    no ``content`` at all. Nothing is wrong with the provider or the
    request: the model drew a bad answer.

    Reaction: try again at once, without the backoff of its parent
    class; a new draw usually gives a code block. Being a
    ``ProviderError``, it is still retried, with backoff, by code that
    does not know this subclass.

    Unlike a rate limit, the attempt was processed: the provider read
    the whole prompt and the model generated the call. Its tokens are
    carried here so that the caller can count them.
    """

    def __init__(
        self, message: str, input_tokens: int, output_tokens: int
    ) -> None:
        """Store the tokens the discarded attempt consumed.

        Args:
            message: Human-readable description, for the logs.
            input_tokens: Prompt tokens, as reported (or estimated).
            output_tokens: Generated tokens, as reported; often 0, as
                Gemini does not count the filtered call.
        """
        super().__init__(message)
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens

    @property
    def input_tokens(self) -> int:
        """Prompt tokens consumed by the discarded attempt."""
        return self._input_tokens

    @property
    def output_tokens(self) -> int:
        """Generated tokens consumed by the discarded attempt."""
        return self._output_tokens


class BadRequestError(LLMError):
    """The provider rejected the request itself (400, 404, 422...).

    Reaction: no retry, the same request would fail again with any key.
    Typical causes are an unknown model name or a malformed payload.
    """


class LLMCallFailed(LLMError):
    """Every attempt of one call failed: the call gives no answer.

    Raised by ``RotatingClient.complete`` from the last error once at
    least one request was sent. It carries what those requests cost, so
    that the trace counts them even though no answer came back (subject
    V.1.1: ``total_requests`` includes retries).

    The original error stays reachable as ``__cause__``.
    """

    def __init__(
        self,
        cause: LLMError,
        attempts: int,
        input_tokens: int,
        output_tokens: int,
        request_time_ms: float,
    ) -> None:
        """Store the cost of the failed call.

        Args:
            cause: The error of the last attempt; its text is reused.
            attempts: Requests actually sent, at least 1.
            input_tokens: Prompt tokens the attempts consumed (only
                native tool calls report any).
            output_tokens: Generated tokens the attempts consumed.
            request_time_ms: Time of the whole call, waits included.
        """
        super().__init__(str(cause))
        self._attempts = attempts
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        self._request_time_ms = request_time_ms

    @property
    def attempts(self) -> int:
        """Requests actually sent during the call."""
        return self._attempts

    @property
    def input_tokens(self) -> int:
        """Prompt tokens consumed by the failed attempts."""
        return self._input_tokens

    @property
    def output_tokens(self) -> int:
        """Generated tokens consumed by the failed attempts."""
        return self._output_tokens

    @property
    def request_time_ms(self) -> float:
        """Time of the whole call, in milliseconds."""
        return self._request_time_ms
