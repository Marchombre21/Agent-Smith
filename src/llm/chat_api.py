"""One HTTP call to an OpenAI-compatible ``/chat/completions`` endpoint."""

import logging
import time
from collections.abc import Callable, Sequence
from typing import Any

import httpx

from src.llm.config import ApiKey, ProviderConfig
from src.llm.errors import (
    AuthError,
    BadRequestError,
    NativeToolCallError,
    ProviderError,
    RateLimitError,
)
from src.llm.models import LLMResponse, Message


class ChatCompletionsApi:
    """Sends a single chat request to one provider, with the key it is given.

    This class makes exactly one attempt: it does not choose keys, retry or
    wait. On failure it raises an ``LLMError`` subclass and lets the caller
    (the retry policy) decide what to do.

    The ``httpx.Client`` is injected so that tests can pass one built on
    ``httpx.MockTransport`` and never touch the network; the ``clock``
    (``time.perf_counter`` by default) measures the request time.
    """

    _log = logging.getLogger(__name__)
    # Rough ratio used only when "usage" is missing or impossible. 3 rather
    # than 4: measured 3.0-3.8, and overestimating protects the budget.
    _CHARS_PER_TOKEN = 3
    # Length of the response body quoted in error messages.
    _BODY_EXCERPT = 300

    def __init__(
        self,
        provider: ProviderConfig,
        model_name: str,
        http: httpx.Client,
        temperature: float = 0.0,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        """Bind the API to one provider and one model.

        Args:
            provider: Where to send requests (base URL, key prefix).
            model_name: Model identifier as the provider spells it,
                e.g. ``"llama-3.3-70b-versatile"``.
            http: HTTP client; its timeout applies to each request.
            temperature: Sampling temperature; 0 makes answers as
                reproducible as the provider allows.
            clock: Returns seconds; only differences are used.

        Raises:
            ValueError: ``model_name`` is empty.
        """
        if not model_name.strip():
            raise ValueError("model_name must not be empty")
        self._provider = provider
        self._model_name = model_name
        self._http = http
        self._temperature = temperature
        self._clock = clock

    def send(
        self,
        key: ApiKey,
        messages: Sequence[Message],
        *,
        stop: Sequence[str] = (),
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> LLMResponse:
        """Make one chat request with ``key`` and return the answer.

        Args:
            key: The API key to authenticate with, chosen by the caller.
            messages: The whole conversation, system prompt first.
            stop: Strings at which the model must stop generating.
            max_tokens: Upper bound on generated tokens; None leaves the
                provider's default.
            timeout: HTTP timeout in seconds for this request, typically
                the time left on the task; None keeps the timeout of the
                injected ``httpx.Client``.

        Raises:
            ValueError: ``timeout`` is zero or negative.
            RateLimitError: HTTP 429.
            AuthError: HTTP 401 or 403.
            ProviderError: Timeout, network failure, 408, 5xx or a body
                that is not a chat completion.
            BadRequestError: Any other 4xx.
        """
        payload = self._payload(messages, stop, max_tokens)
        response, elapsed_ms = self._post(key, payload, timeout)
        self._check_status(response)
        return self._to_response(response, elapsed_ms, messages)

    def _endpoint(self, key: ApiKey) -> str:
        """Return the full URL of the chat endpoint for ``key``.

        Providers like Cloudflare put the account id in the URL; it is
        taken from the key, since each key belongs to one account.

        Raises:
            ValueError: The URL needs an account id and ``key`` has none.
        """
        base_url = self._provider.base_url
        if "{account_id}" in base_url:
            if key.account_id is None:
                raise ValueError(f"{key.env_name} has no account id")
            base_url = base_url.replace("{account_id}", key.account_id)
        return f"{base_url}/chat/completions"

    def _headers(self, key: ApiKey) -> dict[str, str]:
        """Return the HTTP headers of a request authenticated with ``key``.

        This is the only place where the secret leaves its ``SecretStr``.
        """
        return {
            "Authorization": f"Bearer {key.value.get_secret_value()}",
            "Content-Type": "application/json",
        }

    def _payload(
        self,
        messages: Sequence[Message],
        stop: Sequence[str],
        max_tokens: int | None,
    ) -> dict[str, Any]:
        """Return the JSON body of a chat request.

        ``stop`` and ``max_tokens`` are left out when unset: some providers
        reject an empty ``stop`` list or a null ``max_tokens``.
        """
        payload: dict[str, Any] = {
            "model": self._model_name,
            "messages": [message.model_dump() for message in messages],
            "temperature": self._temperature,
        }
        if stop:
            payload["stop"] = list(stop)
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        return payload

    def _post(
        self,
        key: ApiKey,
        payload: dict[str, Any],
        timeout: float | None = None,
    ) -> tuple[httpx.Response, float]:
        """Send ``payload`` with ``key``; return the response and its time.

        Any HTTP status comes back as a response, error statuses included:
        reading them is the caller's job. Only failures with no response at
        all (timeout, DNS, refused connection) are raised here.

        Returns:
            The raw response and the elapsed time in milliseconds.

        Raises:
            ValueError: ``timeout`` is zero or negative.
            ProviderError: The request timed out or never got an answer.
        """
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be positive")
        start = self._clock()
        try:
            response = self._http.post(
                self._endpoint(key),
                headers=self._headers(key),
                json=payload,
                timeout=(
                    httpx.USE_CLIENT_DEFAULT if timeout is None else timeout
                ),
            )
        except httpx.TimeoutException as exc:
            raise ProviderError(f"{self._provider.name}: timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"{self._provider.name}: {type(exc).__name__}: {exc}"
            ) from exc
        return response, (self._clock() - start) * 1000

    def _check_status(self, response: httpx.Response) -> None:
        """Raise the error matching an unsuccessful HTTP status.

        Returns silently on 2xx. The mapping is chosen by what the caller
        should do next, see ``src/llm/errors.py``.
        """
        status = response.status_code
        if response.is_success:
            return
        detail = (
            f"{self._provider.name}: HTTP {status}: "
            f"{response.text[: self._BODY_EXCERPT]}"
        )
        if status == 429:
            raise RateLimitError(detail, self._retry_after(response))
        if status in (401, 403):
            raise AuthError(detail)
        if status == 408 or status >= 500:
            raise ProviderError(detail)
        raise BadRequestError(detail)

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        """Read the ``Retry-After`` header as seconds, or None.

        The header may also hold an HTTP date; that form is rare on LLM
        APIs and is treated as absent.
        """
        value = response.headers.get("retry-after")
        if value is None:
            return None
        try:
            seconds = float(value)
        except ValueError:
            return None
        return seconds if seconds >= 0 else None

    def _to_response(
        self,
        response: httpx.Response,
        elapsed_ms: float,
        messages: Sequence[Message],
    ) -> LLMResponse:
        """Turn a successful response body into an ``LLMResponse``.

        Token counts come from ``_token_counts``.

        Raises:
            NativeToolCallError: No text came back because the model
                attempted a native tool call (filtered by Gemini, or
                passed in ``tool_calls``). Checked before ``content``,
                which Gemini then leaves out.
            ProviderError: The body is not the expected JSON (some
                providers answer 200 with an error object).
        """
        try:
            data = response.json()
            choice = data["choices"][0]
            message = choice["message"]
            if not message.get("content") and (
                "MALFORMED_FUNCTION_CALL" in str(choice.get("finish_reason"))
                or message.get("tool_calls")
            ):
                raise NativeToolCallError(
                    f"{self._provider.name}: native tool call, no text "
                    f"(finish_reason {choice.get('finish_reason')})"
                )
            text = message["content"] or ""
        except (
            ValueError, KeyError, IndexError, TypeError, AttributeError
        ) as exc:
            raise ProviderError(
                f"{self._provider.name}: unexpected response body: "
                f"{response.text[: self._BODY_EXCERPT]}"
            ) from exc
        input_tokens, output_tokens = self._token_counts(
            data.get("usage") or {}, text, messages
        )
        model = data.get("model")
        return LLMResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            request_time_ms=elapsed_ms,
            retries=0,
            api_url=self._provider.base_url,
            model_name=model if isinstance(model, str) else self._model_name,
        )

    def _token_counts(
        self,
        usage: dict[str, Any],
        text: str,
        messages: Sequence[Message],
    ) -> tuple[int, int]:
        """Return ``(input_tokens, output_tokens)`` for one response.

        The provider's figures are kept whenever they are plausible, and
        only ever raised: hidden reasoning that is counted in
        ``total_tokens`` alone is added to the output. They are replaced
        by an estimate from text length, with a warning, in two cases:

        - ``usage`` is missing or not made of integers;
        - the output is 0 although text came back. Gemini does this when
          it filters a native function call the model attempted
          (``finish_reason`` ``MALFORMED_FUNCTION_CALL``). The tokens of
          the filtered call are lost, so the estimate is a lower bound.

        Reporting 0 instead would let the task overrun its token limits
        unnoticed and make ``solution.json`` lie.

        Args:
            usage: The ``usage`` object of the body, ``{}`` if absent.
            text: The generated text.
            messages: The conversation sent, to estimate the input.
        """
        input_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")
        if not isinstance(input_tokens, int) or not isinstance(
            output_tokens, int
        ):
            self._log.warning(
                "%s: no token usage in response, estimating",
                self._provider.name,
            )
            prompt_chars = sum(len(message.content) for message in messages)
            return (
                prompt_chars // self._CHARS_PER_TOKEN,
                len(text) // self._CHARS_PER_TOKEN,
            )
        total = usage.get("total_tokens")
        if isinstance(total, int):
            output_tokens = max(output_tokens, total - input_tokens)
        if output_tokens == 0 and text:
            self._log.warning(
                "%s: 0 output tokens reported for %d characters, estimating",
                self._provider.name,
                len(text),
            )
            output_tokens = max(1, len(text) // self._CHARS_PER_TOKEN)
        return input_tokens, output_tokens
