import io
import json
import sys
from contextlib import redirect_stdout
from resource import setrlimit, RLIMIT_AS


def main():
    max_memory = 512 * 1024 * 1024
    setrlimit(RLIMIT_AS, (max_memory, max_memory))
    globals_values = {}

    while True:
        line = sys.stdin.readline()
        if line == "":
            break
        code = json.loads(line)["code"]
        buffer = io.StringIO()
        try:
            with redirect_stdout(buffer):
                exec(code, globals_values)
        except Exception as e:
            buffer.write(f"{type(e).__name__}: {e}\n")
        sys.stdout.write(json.dumps({"output": buffer.getvalue()}) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
