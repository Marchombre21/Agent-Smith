"""Worker process of the sandbox: executes untrusted code in isolation.

Launched by 'Sandbox.start()' with the sandbox config as a JSON
argument. It reads one JSON message per line on stdin
('{"code": ...}') and answers one JSON line per execution on stdout
('{"stdout": ..., "error": ..., "memory_exceeded": ...}').
"""

import builtins
import io
import json
import traceback
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType
from typing import Any, IO, Mapping, Sequence, NoReturn


class FinalAnswerSignal(BaseException):
    """Raised by final_answer() to stop the execution
    """


def final_answer(code: Any) -> NoReturn:
    """Ends the execution and hands value to the agent as the final answer.

    Args:
        code: The final code.
    """
    raise FinalAnswerSignal(code)


def main() -> None:
    """Run the execution loop of the worker.

    Restricts imports and file access, then executes each code received
    on stdin in this restricted namespace, until stdin is closed.
    Variables are kept from one execution to the next. The output of
    the code is captured, so that it cannot corrupt the JSON messages
    sent to the parent.
    """
    config = json.loads(sys.argv[1])
    list_tools = sys.argv[2]
    # print(list_tools)
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
    builtins_dict_copy["list_tools"] = list_tools

    globals_values = {"__builtins__": builtins_dict_copy}

    while True:
        line = sys.stdin.readline()
        if line == "":
            break
        code = json.loads(line)["code"]
        buffer = io.StringIO()
        error, memory_exceeded, answer = None, False, None
        try:
            with redirect_stdout(buffer):
                exec(code, globals_values)
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
                    "stdout": buffer.getvalue(),
                    "error": error,
                    "memory_exceeded": memory_exceeded,
                    "answer": answer
                }
            )
            + "\n"
        )
        sys.stdout.flush()


if __name__ == "__main__":
    main()
