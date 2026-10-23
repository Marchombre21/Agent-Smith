import sys
from src.sandbox.sandbox import Sandbox
from src.sandbox.execution_result import ExecutionResult


def run_repl(sandbox: Sandbox) -> None:
    while True:
        line = sys.stdin.readline()
        if line == "":
            break
        result: ExecutionResult = sandbox.execute(line)
        print(result.output, end="")
