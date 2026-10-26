import readline  # noqa: F401  (enables arrow keys/history in input())
import codeop
from src.sandbox.sandbox import Sandbox
from src.sandbox_port import ExecutionResult


def run_repl(sandbox: Sandbox) -> None:
    """Run an interactive prompt that executes each entry in the sandbox.

    An entry can span several lines, as in the Python REPL: after each
    line, the whole entry is checked with codeop. While it is
    incomplete (after "def f():"), a "..." prompt asks for the
    next line, and an empty line closes the block. A complete entry, or
    one with a syntax error, is executed in the sandbox, then its
    output, its error and what happened to the worker (timeout, lost
    variables) are printed. The loop stops on "exit" or EOF (Ctrl+D);
    Ctrl+C is not caught here, so that the caller can close the sandbox.

    Args:
        sandbox: An already started sandbox.
    """

    lines: list[str] = []
    while True:

        try:
            line = input("... " if lines else ">>> ")
        except EOFError:
            print()
            break
        if not lines:
            if line.strip() == "exit":
                break
            if line.strip() == "":
                continue
        lines.append(line)
        try:
            incomplete = codeop.compile_command("\n".join(lines)) is None
        except Exception:
            incomplete = False
        if incomplete:
            continue
        result: ExecutionResult = sandbox.execute("\n".join(lines))
        lines = []
        print(result.stdout, end="")
        if result.error:
            print(result.error.rstrip("\n"))
        if result.timed_out:
            print("Timeout: execution killed")
        if result.state_reset:
            print("Variables lost")
