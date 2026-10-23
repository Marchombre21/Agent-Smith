import builtins
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType
from typing import Any, IO, Mapping, Sequence


def main() -> None:
    config = json.loads(sys.argv[1])
    real_builtins = vars(builtins)
    real_open = builtins.open
    real_import = builtins.__import__
    builtins_dict_copy = dict(real_builtins)

    def check_import(
        name: str,
        globals: Mapping[str, object] | None = None,
        locals: Mapping[str, object] | None = None,
        fromlist: Sequence[str] | None = (),
        level: int = 0,
    ) -> ModuleType:
        pattern = f"{name.split('.')[0]}.*"
        authorized = config["authorized_imports"]
        if name not in authorized and pattern not in authorized:
            raise ImportError(f"Import of '{name}' is not allowed")
        module: ModuleType = real_import(
            name, globals, locals, fromlist, level
            )
        return module

    def check_access_files(path: str, *args: Any, **kwargs: Any) -> IO[Any]:
        real_path = Path(path).resolve()
        for auth_path in config["allowed_directories"]:
            if real_path.is_relative_to(auth_path):
                file: IO[Any] = real_open(path, *args, **kwargs)
                return file
        raise PermissionError(f"Cannot access to {real_path}.")

    builtins_dict_copy["open"] = check_access_files
    builtins_dict_copy["__import__"] = check_import

    globals_values = {"__builtins__": builtins_dict_copy}

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
