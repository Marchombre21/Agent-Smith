"""Rotation over the API keys of one provider."""

import time
from collections.abc import Callable, Sequence

from src.llm.config import ApiKey


class KeyPool:
    """Hands out a provider's API keys, skipping those that are rate limited.

    The pool sticks to one key as long as it works and moves to the next
    one only when the current key is blocked (rate limit or exhausted
    quota). Blocking is temporary: a key becomes usable again once its
    waiting time is over.

    Time is read through an injectable ``clock`` (``time.monotonic`` by
    default), so the behaviour can be tried without actually waiting.
    """

    def __init__(
        self,
        keys: Sequence[ApiKey],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Create a pool over ``keys``, used in the given order.

        Raises:
            ValueError: ``keys`` is empty.
        """
        if not keys:
            raise ValueError("a key pool needs at least one key")
        self._keys: list[ApiKey] = list(keys)
        self._clock = clock
        self._current = 0
        self._blocked_until: dict[str, float] = {}

    def acquire(self) -> ApiKey | None:
        """Return the key to use now, or None if every key is blocked.

        Starts from the current key and walks the list in order, wrapping
        around, until it finds a key that is not blocked; that key becomes
        the current one.
        """
        now = self._clock()
        for offset in range(len(self._keys)):
            index = (self._current + offset) % len(self._keys)
            key = self._keys[index]
            if self._blocked_until.get(key.env_name, 0.0) <= now:
                self._current = index
                return key
        return None

    def block(self, key: ApiKey, seconds: float) -> None:
        """Set ``key`` aside for ``seconds``, e.g. after a 429 response.

        Blocking a key that is already blocked keeps the later of the two
        release times, so a short wait never shortens a longer one.

        Raises:
            ValueError: ``key`` is not in this pool, or ``seconds`` is
                negative.
        """
        if all(k.env_name != key.env_name for k in self._keys):
            raise ValueError(f"{key.env_name} is not in this pool")
        if seconds < 0:
            raise ValueError("seconds must be zero or positive")
        until = self._clock() + seconds
        previous = self._blocked_until.get(key.env_name, 0.0)
        self._blocked_until[key.env_name] = max(previous, until)

    def wait_time(self) -> float:
        """Return how many seconds until a key is usable, 0.0 if one is now.

        When every key is blocked, this is the delay before the first one
        is released; the caller can sleep that long, or give up if it goes
        past its deadline.
        """
        now = self._clock()
        earliest = min(
            self._blocked_until.get(key.env_name, 0.0) for key in self._keys
        )
        return max(0.0, earliest - now)
