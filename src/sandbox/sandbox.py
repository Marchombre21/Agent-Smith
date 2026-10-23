import json
import select
import sys

from typing import Any, IO
from src.sandbox.execution_result import ExecutionResult
from src.sandbox.ConfigSandbox import SandboxConfig
from pathlib import Path
from resource import RLIMIT_AS, setrlimit
from subprocess import PIPE, Popen, TimeoutExpired


class Sandbox:
    def __init__(self, config: SandboxConfig) -> None:
        self.config = config
        self.max_time = config.max_execution_time_seconds
        self.memory = config.max_memory_mb
        self.proc: Popen[str] | None = None

    def start(self) -> None:
        worker = Path(__file__).parent / "worker.py"
        if not worker.exists():
            raise FileNotFoundError(f"Worker not found: {worker}")
        max_mem_mo = self.memory * 1024 * 1024
        self.proc = Popen(
            [sys.executable, "-I", worker, self.config.model_dump_json()],
            stdin=PIPE,
            stdout=PIPE,
            text=True,
            preexec_fn=lambda: setrlimit(RLIMIT_AS, (max_mem_mo, max_mem_mo)),
        )

    def execute(self, code: str) -> ExecutionResult:
        _, stdin, stdout = self._pipes
        result = ExecutionResult(output="")
        stdin.write(json.dumps({"code": code}) + "\n")
        stdin.flush()

        ready, _, _ = select.select([stdout], [], [], self.max_time)
        if not ready:
            self._restart(True, result)
            return result

        brut_answer = stdout.readline()

        # If the answer is "" it means that the worker process died for
        # unknown reason (maybe a sys.exit() from the code).
        if brut_answer == "":
            self._restart(False, result)
            return result

        result.output = json.loads(brut_answer)["output"]
        return result

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
            raise RuntimeError("Sandbox is not started")
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
        self.proc = None

    def _restart(self, timed_out: bool, result: ExecutionResult) -> None:
        proc, _, _ = self._pipes
        if timed_out:
            proc.kill()
            result.timed_out = True
            result.output = "Timeout: execution killed, variables lost"
        else:
            result.crashed = True
            result.output = "Execution killed, variables lost"

        proc.wait()
        self.start()
