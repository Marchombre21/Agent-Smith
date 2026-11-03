"""Turn the moulinette's SIGTERM into an exception the CLI can handle."""

import signal
from types import FrameType
from typing import Any, Callable, Optional, Union


class TerminationRequested(BaseException):
    """SIGTERM was received: stop now and write what is known.

    A ``BaseException``, like ``KeyboardInterrupt``: no ``except
    Exception`` on the way (ours or the sandbox's) can swallow it, so it
    reaches the CLI, and every ``with`` block it crosses is closed on
    the way up (sandbox, MCP server, later the Docker container).
    """


class TerminationGuard:
    """Context manager that raises ``TerminationRequested`` on SIGTERM.

    At its time limit the moulinette sends SIGTERM to the whole process
    group, then SIGKILL 10 s later. Python's default reaction to SIGTERM
    is to die at once, without running ``finally`` or ``__exit__``: no
    ``solution.json``, no cleanup. Inside this guard, SIGTERM becomes an
    exception instead. The previous handler is put back on exit.

    Signal handlers can only be set from the main thread, which is where
    the CLI runs.
    """

    def __init__(self) -> None:
        """Prepare the guard; nothing is installed before ``with``."""
        self._previous: Union[
            Callable[[int, Optional[FrameType]], Any], int, None
        ] = None

    def __enter__(self) -> "TerminationGuard":
        """Install the handler, keeping the one it replaces."""
        self._previous = signal.signal(signal.SIGTERM, self._on_sigterm)
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        """Put the previous handler back; never suppress an exception."""
        previous = self._previous
        if previous is None:
            previous = signal.SIG_DFL
        signal.signal(signal.SIGTERM, previous)

    def _on_sigterm(self, signum: int, frame: Optional[FrameType]) -> None:
        """Ignore further SIGTERMs, then stop the run with an exception.

        Ignoring the next ones lets ``solution.json`` be written to the
        end even if a second signal comes.
        """
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        raise TerminationRequested(f"terminated by signal {signum}")
