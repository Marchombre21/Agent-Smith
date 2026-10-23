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
        )

    def __enter__(self) -> "Sandbox":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
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
