import json
import select
import sys
from ConfigSandbox import SandboxConfig
from subprocess import Popen, PIPE
from pathlib import Path
from resource import setrlimit, RLIMIT_AS


def start_worker(config: SandboxConfig):
    worker = Path(__file__).parent / "worker.py"
    max_mem_mo = config.max_memory_mb * 1024 * 1024
    return Popen([sys.executable, '-I', worker, config.model_dump_json()],
                 stdin=PIPE,
                 stdout=PIPE,
                 text=True,
                 preexec_fn=lambda: setrlimit(RLIMIT_AS,
                                              (max_mem_mo, max_mem_mo)))


def reborn(proc: Popen, timed_out: bool, config: SandboxConfig) -> Popen:
    if timed_out:
        proc.kill()
        print("Timeout: execution killed, variables lost")
    else:
        print("Execution killed, variables lost")

    proc.wait()
    return start_worker(config)


def main():
    config = SandboxConfig()
    proc = start_worker(config)

    while True:
        line = sys.stdin.readline()
        if line == "":
            break
        proc.stdin.write(json.dumps({"code": line}) + "\n")
        proc.stdin.flush()

        ready, _, _ = select.select([proc.stdout], [], [],
                                    config.max_execution_time_seconds)
        if not ready:
            proc = reborn(proc, True, config)
            continue

        brut_answer = proc.stdout.readline()

        # If the answer is "" it means that the process died for unknown
        # reason (maybe a sys.exit() from the code).
        if brut_answer == "":
            proc = reborn(proc, False, config)
            continue

        answer = json.loads(brut_answer)
        print(answer["output"], end="")

    proc.stdin.close()
    proc.wait()


if __name__ == "__main__":
    main()
