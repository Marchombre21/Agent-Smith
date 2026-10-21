import json
import select
import sys
from subprocess import Popen, PIPE
from pathlib import Path


def start_worker():
    worker = Path(__file__).parent / "worker.py"
    return Popen([sys.executable, '-I', worker],
                 stdin=PIPE, stdout=PIPE, text=True)


def main():
    proc = start_worker()

    while True:
        line = sys.stdin.readline()
        if line == "":
            break
        proc.stdin.write(json.dumps({"code": line}) + "\n")
        proc.stdin.flush()

        ready, _, _ = select.select([proc.stdout], [], [], 15)
        if not ready:
            proc.kill()
            proc.wait()
            print("Timeout: execution killed, variables lost")
            proc = start_worker()
            continue
        answer = json.loads(proc.stdout.readline())
        print(answer["output"], end="")

    proc.stdin.close()
    proc.wait()


if __name__ == "__main__":
    main()
