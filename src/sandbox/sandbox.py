import json
import select
import sys

from src.sandbox_port import ExecutionResult, SandboxError, SandboxPort
from typing import Any, IO
from src.models import SandboxConfig
from pathlib import Path
from resource import RLIMIT_AS, setrlimit
from subprocess import PIPE, Popen, TimeoutExpired


class Sandbox(SandboxPort):
    """Executes untrusted code in a separate, restricted worker process.

    The worker keeps its variables between executions. It is restarted
    when it exceeds the time limit or dies, which loses its variables.
    Use it as a context manager so that the worker is always stopped:

        with Sandbox(config) as sandbox:
            result = sandbox.execute("print(1 + 1)")
    """
    def __init__(self, config: SandboxConfig) -> None:
        self.config = config
        self.max_time = config.max_execution_time_seconds
        self.memory = config.max_memory_mb
        self.proc: Popen[str] | None = None

    def start(self) -> None:
        """Start the worker process that will execute the submitted code.

        The worker runs in its own process, isolated from the sandbox,
        with the limits defined in the configuration.

        Raises:
            SandboxError: If the worker script cannot be found.
        """
        worker = Path(__file__).parent / "worker.py"
        if not worker.exists():
            raise SandboxError(f"Worker not found: {worker}")
        max_mem_mo = self.memory * 1024 * 1024
        self.proc = Popen(
            [sys.executable, "-I", worker, self.config.model_dump_json()],
            stdin=PIPE,
            stdout=PIPE,
            text=True,
            start_new_session=True,
            preexec_fn=lambda: setrlimit(RLIMIT_AS, (max_mem_mo, max_mem_mo)),
        )

    def execute(
        self, code: str, timeout: float | None = None
    ) -> ExecutionResult:
        """Execute code in the worker process (see ``SandboxPort.execute``).

        The code is sent to the worker, then the sandbox waits for its
        answer for at most the smaller of ``timeout`` and the configured
        time limit. If the time limit is exceeded, the worker is killed;
        if it died, or was killed, a new one is started and the result
        reports ``state_reset``.

        Args:
            code: Python source to execute.
            timeout: Seconds allowed for this execution; None means the
                limit of the sandbox configuration.

        Returns:
            What happened during the execution. Errors of the code itself
            are reported in it, never raised.

        Raises:
            SandboxError: If the sandbox is not started.
        """
        _, stdin, stdout = self._pipes
        limit = (
            self.max_time if timeout is None else min(timeout, self.max_time)
        )
        stdin.write(json.dumps({"code": code}) + "\n")
        stdin.flush()

        ready, _, _ = select.select([stdout], [], [], limit)
        if not ready:
            self._restart(kill=True)
            return ExecutionResult(timed_out=True, state_reset=True)

        brut_answer = stdout.readline()

        # If the answer is "" it means that the worker process died for
        # unknown reason (maybe a sys.exit() from the code).
        if brut_answer == "":
            exit_code = self._restart(kill=False)
            return ExecutionResult(
                state_reset=True,
                error=f"Worker process exited with code {exit_code}",
            )

        answer = json.loads(brut_answer)
        return ExecutionResult(
            stdout=answer["stdout"],
            error=answer["error"],
            memory_exceeded=answer["memory_exceeded"],
            final_answer=answer["answer"]
        )

    def __enter__(self) -> "Sandbox":
        """Start the worker when entering a ``with`` block.

        Returns:
            The sandbox itself, bound by ``with ... as``.
        """
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        """Close the worker when leaving a ``with`` block.

        Called even if an exception was raised; the exception is not
        suppressed, so that it reaches the caller.
        """
        self.close()

    @property
    def _pipes(self) -> tuple[Popen[str], IO[str], IO[str]]:
        """Return the running worker and its pipes, or raise if not started."""
        if (
            self.proc is None
            or self.proc.stdin is None
            or self.proc.stdout is None
        ):
            raise SandboxError("Sandbox is not started")
        return self.proc, self.proc.stdin, self.proc.stdout

    def close(self) -> None:
        """Close the worker properly.
        """
        if self.proc is None:
            return
        if self.proc.stdin is not None:
            self.proc.stdin.close()
        try:
            self.proc.wait(timeout=2)
        except TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        if self.proc.stdout is not None:
            self.proc.stdout.close()
        self.proc = None

    def _restart(self, kill: bool) -> int | None:
        """Replace the worker with a new one and return the old one's exit
        code."""
        proc, _, _ = self._pipes
        if kill:
            proc.kill()
        self.close()
        self.start()
        return proc.returncode

    def manual(self) -> str:
        return "No tools available"
