"""Worker process of the sandbox: executes untrusted code in isolation.

Launched by 'Sandbox.start()' with the sandbox config and the names of
the MCP tools as JSON arguments. It talks with the parent with one JSON
message per line:

- parent -> worker: '{"code": ...}', the code to execute.
- worker -> parent, during the execution:
    - '{"exec_stdout": ...}' for each write() of the code, sent at once
      so that the output survives if the worker is killed;
    - '{"tool_call": ..., "args": ..., "kwargs": ...}' when the code
      calls an MCP tool; the worker then waits for the parent's answer
      '{"result": ..., "error": ...}' on stdin.
- worker -> parent, at the end: '{"error": ..., "memory_exceeded": ...,
  "answer": ..., "interrupt": ..., "exit_code": ...}'.
"""

import builtins
import json
import ast
import traceback
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType
from typing import Any, IO, Mapping, Sequence, NoReturn, TextIO, Callable

RESTRICTED = [
    "eval",
    "exec",
    "compile",
    "globals",
    "vars",
    "getattr",
    "setattr",
    "delattr",
    "breakpoint",
    "help",
    "input",
]


class FalseStdout:
    """Replace the real_stdout to send results at each write() rather than as a
    single batch. To recover partial data in the event of a kill.
    """

    def __init__(self, real_stdout: IO[str]) -> None:
        self.real_stdout = real_stdout

    def write(self, text: str) -> int:
        self.real_stdout.write(json.dumps({"exec_stdout": text}) + "\n")
        self.flush()
        return len(text)

    def flush(self) -> None:
        self.real_stdout.flush()


class ToolCallError(Exception):
    """Raised when an error occured in MCP server during code execution."""


class FinalAnswerSignal(BaseException):
    """Raised by final_answer() to stop the execution"""


def final_answer(code: Any) -> NoReturn:
    """Ends the execution and hands value to the agent as the final answer.

    Args:
        code: The final code.
    """
    raise FinalAnswerSignal(code)


def my_exit(code: object = None) -> NoReturn:
    """Replace real exit and quit functions builtins because these functions
    close the stdin before raise SystemExit. Then the worker crash when
    readline().
    """
    raise SystemExit(code)


def _make_tool(name: str, stdout: TextIO | Any) -> Callable[..., Any]:

    def tool(*args: Any, **kwargs: Any) -> Any:
        stdout.write(
            json.dumps(
                {"tool_call": name, "args": list(args), "kwargs": kwargs}
            )
            + "\n"
        )
        stdout.flush()
        answer = json.loads(sys.stdin.readline())
        if answer["error"] is not None:
            raise ToolCallError(answer["error"])
        return answer["result"]

    return tool


def _check_code(code: str) -> None:
    """Before execution, an AST parser denies access to any attribute that
    starts with an underscore, because that's how you can trace back to the
    actual modules (__globals__, __self__, __subclasses__).

    Args:
        code (str): The code to parse.

    Raises:
        PermissionError: The raised error in case of an attribute with _.
    """
    parsed_code = ast.parse(code)
    for node in ast.walk(parsed_code):
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                raise PermissionError(
                    f"You are not allowed to access {node.attr} attribute."
                )


def _restrict_builtins(name: str) -> Callable[..., Any]:

    def raiser(*args: Any, **kwargs: Any) -> Any:
        raise PermissionError(f"You are not allowed to use {name} function.")

    return raiser


def main() -> None:
    """Run the execution loop of the worker.

    Restricts imports and file access, then executes each code received
    on stdin in this restricted namespace, until stdin is closed.
    Variables are kept from one execution to the next. The output of
    the code is captured, so that it cannot corrupt the JSON messages
    sent to the parent.
    """
    config = json.loads(sys.argv[1])
    real_stdout = sys.stdout
    list_tools = json.loads(sys.argv[2])
    real_builtins = vars(builtins)
    real_open = builtins.open
    real_import = builtins.__import__
    builtins_dict_copy = dict(real_builtins)
    builtins_dict_copy["final_answer"] = final_answer

    def check_import(
        name: str,
        globals: Mapping[str, object] | None = None,
        locals: Mapping[str, object] | None = None,
        fromlist: Sequence[str] | None = (),
        level: int = 0,
    ) -> ModuleType:
        """Import a module only if it is in the authorized imports.

        Replaces ``__import__`` in the builtins of the executed code. A
        module is allowed if its exact name is in the list, or if
        ``<top-level package>.*`` is (e.g. ``collections.*`` allows
        ``collections.abc``).

        Returns:
            The imported module, from the real ``__import__``.

        Raises:
            ImportError: If the module is not allowed.
        """
        pattern = f"{name.split('.')[0]}.*"
        authorized = config["authorized_imports"]
        if name not in authorized and pattern not in authorized:
            raise ImportError(f"Import of '{name}' is not allowed")
        module: ModuleType = real_import(
            name, globals, locals, fromlist, level
        )
        return module

    def check_access_files(path: str, *args: Any, **kwargs: Any) -> IO[Any]:
        """Open a file only if it is inside an allowed directory.

        Replaces ``open`` in the builtins of the executed code. The path
        is resolved first (``..`` and symbolic links), so that it cannot
        escape the allowed directories.

        Returns:
            The opened file, from the real ``open``.

        Raises:
            PermissionError: If the file is outside the allowed
                directories.
        """
        real_path = Path(path).resolve()
        for auth_path in config["allowed_directories"]:
            if real_path.is_relative_to(auth_path):
                file: IO[Any] = real_open(path, *args, **kwargs)
                return file
        raise PermissionError(f"Cannot access to {real_path}.")

    builtins_dict_copy["open"] = check_access_files
    builtins_dict_copy["__import__"] = check_import
    builtins_dict_copy["exit"] = my_exit
    builtins_dict_copy["quit"] = my_exit
    for name in RESTRICTED:
        builtins_dict_copy[name] = _restrict_builtins(name)

    for name in list_tools:
        builtins_dict_copy[name] = _make_tool(name, real_stdout)

    globals_values = {"__builtins__": builtins_dict_copy}

    while True:
        line = sys.stdin.readline()
        if line == "":
            break
        code = json.loads(line)["code"]
        error, memory_exceeded, answer, interrupt, exit_code = (
            None,
            False,
            None,
            None,
            None,
        )
        try:
            try:
                _check_code(code)
            except (SyntaxError, PermissionError) as e:
                error = "".join(traceback.format_exception_only(type(e), e))
            if error is None:
                with redirect_stdout(FalseStdout(real_stdout)):
                    exec(code, globals_values)
        except KeyboardInterrupt:
            interrupt = "KeyboardInterrupt"
        except SystemExit as e:
            interrupt = "SystemExit"
            if e.code is None:
                exit_code = None
            elif isinstance(e.code, int):
                exit_code = e.code
            else:
                exit_code = 1
        except MemoryError:
            error, memory_exceeded = "MemoryError", True
        except FinalAnswerSignal as e:
            answer = str(e.args[0])
        except Exception as e:
            # Skip the first frame: it is the exec() call of the worker.
            # It is useless for the LLM and reveals the host file path.
            tb = e.__traceback__.tb_next if e.__traceback__ else None
            error = "".join(traceback.format_exception(type(e), e, tb))
        sys.stdout.write(
            json.dumps(
                {
                    "error": error,
                    "memory_exceeded": memory_exceeded,
                    "answer": answer,
                    "interrupt": interrupt,
                    "exit_code": exit_code,
                }
            )
            + "\n"
        )
        sys.stdout.flush()


if __name__ == "__main__":
    main()
