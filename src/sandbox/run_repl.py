import readline     # noqa: F401  (enables arrow keys/history in input())
from src.sandbox.sandbox import Sandbox
from src.sandbox_port import ExecutionResult


def run_repl(sandbox: Sandbox) -> None:

    while True:
        try:
            line = input(">>> ")
        except EOFError:
            print()
            break
        if line.strip() == "exit":
            break
        if line.strip() == "":
            continue
        result: ExecutionResult = sandbox.execute(line)
        print(result.stdout, end="")
        if result.error:
            print(result.error.rstrip("\n"), end="")
        if result.timed_out:
            print("Timeout: execution killed")
        if result.state_reset:
            print("Variables lost")
