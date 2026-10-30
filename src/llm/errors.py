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
    """


class BadRequestError(LLMError):
    """The provider rejected the request itself (400, 404, 422...).

    Reaction: no retry, the same request would fail again with any key.
    Typical causes are an unknown model name or a malformed payload.
    """
