import readline     # noqa: F401  (enables arrow keys/history in input())
from src.sandbox.sandbox import Sandbox
from src.sandbox_port import ExecutionResult


def run_repl(sandbox: Sandbox) -> None:
    """Run an interactive prompt that executes each entry in the sandbox.

    Each line typed is executed in the sandbox, then its output, its
    error and what happened to the worker (timeout, lost variables) are
    printed. Empty lines are ignored. The loop stops on ``exit`` or EOF
    (Ctrl+D); Ctrl+C is not caught here, so that the caller can close
    the sandbox.

    Args:
        sandbox: An already started sandbox.
    """

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
