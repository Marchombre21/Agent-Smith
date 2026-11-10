"""The Docker container a SWE-bench task runs in, from start to removal."""

import subprocess
import sys
import uuid
from types import TracebackType
from typing import Any, Callable, Optional, Sequence, Type


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
    removed whatever happens in the ``with`` block.

    No container may outlive the run, so three layers back each other:

    1. A normal end, or an ordinary exception, removes the container
       synchronously and patiently: nothing is in a hurry, and a slow
       Docker daemon must not cost a finished result.
    2. An interruption (SIGTERM becomes ``TerminationRequested``, a
       ``BaseException``) must stay fast: the moulinette sends SIGKILL
       10 s later and ``solution.json`` is still to be written. The
       removal gets a short delay and, if it is not enough, is handed to
       a detached process that outlives ours.
    3. If our process dies without running any code (SIGKILL, crash), the
       container removes itself: it only sleeps for ``lifetime_seconds``
       and ``--rm`` deletes it when it exits.

    The container is removed by its *name*, chosen before ``docker run``:
    if the run is interrupted after Docker created the container but
    before its id was read, ``stop()`` still finds it.
    """

    _NAME_PREFIX = "agent-smith-"
    # Normal end: no rush, but bounded (the task's own deadline is near).
    _STOP_SECONDS = 60.0
    _RETRY_SECONDS = 30.0
    # Interruption: well within the 10 s between SIGTERM and SIGKILL.
    _URGENT_STOP_SECONDS = 5.0
    _INSPECT_SECONDS = 10.0
    # Docker answers these when the container is already gone or being
    # removed (``--rm`` and ``rm -f`` can race): the goal is reached.
    _DONE_MESSAGES = ("No such container", "already in progress")

    def __init__(
        self,
        image: str,
        lifetime_seconds: int,
        runner: Callable[..., "subprocess.CompletedProcess[str]"] = (
            subprocess.run
        ),
        spawner: Callable[..., Any] = subprocess.Popen,
    ) -> None:
        """Prepare a container for ``image``; nothing runs before start().

        Args:
            image: Docker image of the task, e.g.
                ``swebench/sweb.eval.x86_64.sympy_1776_sympy-13480``.
            lifetime_seconds: How long the container stays alive at
                most. Longer than the task's time limit plus the 10 s
                before SIGKILL, so it never cuts a legitimate run; it
                only removes a container nobody removed.
            runner: Runs the ``docker`` commands; ``subprocess.run`` by
                default. Called like it, with ``capture_output``,
                ``text`` and ``timeout``; a fake returning a ready-made
                ``CompletedProcess`` lets the class run without Docker.
            spawner: Starts a command without waiting for it;
                ``subprocess.Popen`` by default. Used for the detached
                removal after an interruption.
        """
        self._image = image
        self._lifetime_seconds = lifetime_seconds
        self._runner = runner
        self._spawner = spawner
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

        ``sleep <lifetime>`` keeps the container alive for that long and
        no longer: the images' own command is ``/bin/bash``, which exits
        at once without a terminal, and ``sleep infinity`` would leave
        the container behind if our process were killed. ``--rm`` makes
        Docker delete the container as soon as ``sleep`` exits.
        No timeout on ``docker run``: Docker may first have to pull the
        image; the task's time limit (SIGTERM) bounds the wait.

        Raises:
            ContainerError: Already started, or ``docker run`` failed.
        """
        if self._name is not None:
            raise ContainerError("the container is already started")
        self._name = f"{self._NAME_PREFIX}{uuid.uuid4().hex[:12]}"
        output = self._docker(
            ["run", "-d", "--rm", "--name", self._name, self._image,
             "sleep", str(self._lifetime_seconds)],
            timeout=None,
        )
        self._id = output.strip()
        return self._id

    def stop(self, urgent: bool = False) -> None:
        """Remove the container, stopping it first if needed.

        Does nothing if the container was never started or is already
        removed, so it can be called more than once. A removal that
        fails or times out is checked with ``docker container inspect``:
        the daemon often finishes after the client gave up.

        Args:
            urgent: Interruption in progress: wait only a few seconds,
                then let a detached process finish the removal instead
                of retrying.

        Raises:
            ContainerError: The container is still there after the
                attempts (patient mode), or the detached removal could
                not be started (urgent mode).
        """
        if self._name is None:
            return
        name = self._name
        self._name = None
        self._id = None
        timeout = self._URGENT_STOP_SECONDS if urgent else self._STOP_SECONDS
        try:
            self._remove(name, timeout)
            return
        except ContainerError as error:
            first_error = error
        if self._is_gone(name):
            return
        if urgent:
            self._remove_in_background(name)
            return
        try:
            self._remove(name, self._RETRY_SECONDS)
        except ContainerError as error:
            if not self._is_gone(name):
                raise ContainerError(
                    f"container {name} is still there after two removals: "
                    f"{first_error}; {error}"
                ) from error

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

        A failed removal is only reported on stderr, never raised: it
        must not replace the error that explains the run, nor turn a
        finished task (patch already computed) into a failure. The
        container's own lifetime is the last safety net.

        An exception that is not an ``Exception`` (``TerminationRequested``
        on SIGTERM, ``KeyboardInterrupt``) is an interruption: the
        removal is urgent.
        """
        urgent = exc_type is not None and not issubclass(exc_type, Exception)
        try:
            self.stop(urgent=urgent)
        except ContainerError as error:
            print(f"cannot remove the container: {error}", file=sys.stderr)

    def _remove(self, name: str, timeout: float) -> None:
        """Run ``docker rm -f`` once; "already gone" counts as success.

        Raises:
            ContainerError: The command failed for another reason.
        """
        try:
            self._docker(["rm", "-f", name], timeout=timeout)
        except ContainerError as error:
            if not any(text in str(error) for text in self._DONE_MESSAGES):
                raise

    def _is_gone(self, name: str) -> bool:
        """Tell whether Docker no longer knows a container of this name.

        Any doubt (``docker`` itself failing to answer in time) means
        "not gone": the caller then tries again or hands over.
        """
        try:
            self._docker(
                ["container", "inspect", name], timeout=self._INSPECT_SECONDS
            )
        except ContainerError as error:
            return "No such" in str(error)
        return False

    def _remove_in_background(self, name: str) -> None:
        """Start ``docker rm -f`` in its own session and do not wait.

        A new session keeps it out of the process group the moulinette
        kills: it goes on after our process has exited.

        Raises:
            ContainerError: The process could not be started.
        """
        try:
            self._spawner(
                ["docker", "rm", "-f", name],
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as error:
            raise ContainerError(
                f"cannot start the detached removal of {name}: {error}"
            ) from error

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
