"""The Docker container a SWE-bench task runs in, from start to removal."""

import subprocess
import sys
import uuid
from types import TracebackType
from typing import Callable, Optional, Sequence, Type


class ContainerError(RuntimeError):
    """A ``docker`` command failed or could not be run.

    A plain ``Exception``: the CLI catches it like any other failure of
    the run and still writes ``solution.json``.
    """


class DockerContainer:
    """One throw-away container for one SWE-bench task.

    ``start()`` runs the task's image in the background; the MCP tools
    then work inside it with ``docker exec`` on ``container_id``.
    ``stop()`` removes it. Used as a context manager, the container is
    removed whatever happens in the ``with`` block, SIGTERM included
    (``TerminationRequested`` crosses the block like any exception).

    The container is removed by its *name*, chosen before ``docker run``:
    if the run is interrupted after Docker created the container but
    before its id was read, ``stop()`` still finds it.
    """

    _NAME_PREFIX = "agent-smith-"
    # The moulinette sends SIGKILL 10 s after SIGTERM: removal must fit
    # well within that, with time left to write solution.json.
    _STOP_TIMEOUT_SECONDS = 5.0

    def __init__(
        self,
        image: str,
        runner: Callable[..., "subprocess.CompletedProcess[str]"] = (
            subprocess.run
        ),
    ) -> None:
        """Prepare a container for ``image``; nothing runs before start().

        Args:
            image: Docker image of the task, e.g.
                ``swebench/sweb.eval.x86_64.sympy_1776_sympy-13480``.
            runner: Runs the ``docker`` commands; ``subprocess.run`` by
                default. Called like it, with ``capture_output``,
                ``text`` and ``timeout``; a fake returning a ready-made
                ``CompletedProcess`` lets the class run without Docker.
        """
        self._image = image
        self._runner = runner
        self._name: Optional[str] = None
        self._id: Optional[str] = None

    @property
    def container_id(self) -> str:
        """The id Docker gave the running container.

        Raises:
            ContainerError: The container is not running.
        """
        if self._id is None:
            raise ContainerError("the container is not running")
        return self._id

    def start(self) -> str:
        """Run the image in the background and return the container id.

        ``sleep infinity`` keeps the container alive: the images' own
        command is ``/bin/bash``, which exits at once without a terminal.
        No timeout: Docker may first have to pull the image; the task's
        time limit (SIGTERM) bounds the wait.

        Raises:
            ContainerError: Already started, or ``docker run`` failed.
        """
        if self._name is not None:
            raise ContainerError("the container is already started")
        self._name = f"{self._NAME_PREFIX}{uuid.uuid4().hex[:12]}"
        output = self._docker(
            ["run", "-d", "--name", self._name, self._image,
             "sleep", "infinity"],
            timeout=None,
        )
        self._id = output.strip()
        return self._id

    def stop(self) -> None:
        """Remove the container, stopping it first if needed.

        Does nothing if the container was never started or is already
        removed, so it can be called more than once.

        Raises:
            ContainerError: ``docker rm`` failed or took too long.
        """
        if self._name is None:
            return
        name = self._name
        self._name = None
        self._id = None
        # rm -f stops and removes in one call; Docker answers 0 even
        # when no container has this name.
        self._docker(["rm", "-f", name], timeout=self._STOP_TIMEOUT_SECONDS)

    def __enter__(self) -> "DockerContainer":
        """Start the container."""
        self.start()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        """Remove the container; never suppress an exception.

        If the block is already failing, a failed removal is only
        reported on stderr: the original error is the one that explains
        the run and must reach the CLI.
        """
        if exc_type is None:
            self.stop()
            return
        try:
            self.stop()
        except ContainerError as error:
            print(f"cannot remove the container: {error}", file=sys.stderr)

    def _docker(self, args: Sequence[str], timeout: Optional[float]) -> str:
        """Run ``docker <args>`` and return its standard output.

        Raises:
            ContainerError: Docker is missing, timed out or exited with a
                non-zero code (its stderr is in the message).
        """
        command = ["docker", *args]
        try:
            done = self._runner(
                command, capture_output=True, text=True, timeout=timeout
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ContainerError(f"{' '.join(command)}: {error}") from error
        if done.returncode != 0:
            raise ContainerError(
                f"{' '.join(command)} exited with {done.returncode}: "
                f"{done.stderr.strip()}"
            )
        return done.stdout
