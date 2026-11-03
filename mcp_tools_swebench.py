import subprocess
import os
from subprocess import CompletedProcess
from pathlib import Path
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

mcp = FastMCP("mcp_tools_swebench")

TESTBED_PATH = os.environ.get("TESTBED_PATH", "")
CONTAINER_ID = os.environ.get("CONTAINER_ID")
EXCLUDED_DIRS = [".venv", ".git", "__pycache__"]

if not TESTBED_PATH:
    raise ValueError("Missing TESTBED_PATH variable to launch MCP server.")


def _run(cmd: list[str]) -> CompletedProcess:
    if CONTAINER_ID:
        final_cmd = ["docker", "exec", "-w", TESTBED_PATH, CONTAINER_ID] + cmd
        final_cwd = None
    else:
        final_cmd = cmd
        final_cwd = TESTBED_PATH
    return subprocess.run(final_cmd,
                          text=True,
                          capture_output=True,
                          cwd=final_cwd)


def _check_path(path: str) -> bool:

    return Path(path).is_relative_to(TESTBED_PATH)


def _truncate(sentence: str, nb_lines: int, msg: str) -> str:
    tmp_datas: list[str] = sentence.splitlines()
    length_datas = len(tmp_datas)
    final: str = f"\n[Truncated: {nb_lines} of {length_datas} {msg}]"
    new_data = "\n".join(tmp_datas[:nb_lines]) + final
    return new_data


@mcp.tool()
def read_file(filepath: str, start_line: int, end_line: int) -> str:
    """Read lines start_line to end_line (1-based, inclusive) of a file.
    Return them as "<line_number>: <line_content>" lines, or a message if
    the file has fewer lines. Raise an error if the file cannot be read.

    Args:
        filepath (str): Path of the file to read, absolute or relative to
            the repository root.
        start_line (int): First line to read (starts at 1).
        end_line (int): Last line to read (included).

    Raises:
        ValueError: If start_line is lower than 1 or greater than end_line.
        ToolError: If the file cannot be read (e.g. it does not exist).
    """

    if start_line < 1:
        raise ValueError("The start_line value cannot be lower than 1.")
    if start_line > end_line:
        raise ValueError("The start_line cannot be greater than end_line.")
    complete_filepath = os.path.normpath(os.path.join(TESTBED_PATH, filepath))
    if _check_path(complete_filepath):
        cmd: list[str] = [
            "sed",
            "-n",
            f"{start_line},{end_line}p",
            "--",
            complete_filepath,
        ]
        result = ""
        run_return: CompletedProcess[str] = _run(cmd=cmd)
        if run_return.returncode != 0:
            code = run_return.returncode
            raise ToolError("The tool execution failed with code"
                            f" {code}:\n{run_return.stderr}")
        response = run_return.stdout.splitlines()
        for number, line in enumerate(response, start=start_line):
            result += f"{number}: {line}\n"
        if result == "":
            return "No lines in range, file has fewer lines."
        return result
    else:
        raise ToolError(f"You cannot access outside of {TESTBED_PATH}")


@mcp.tool()
def list_files(directory: str, pattern: str) -> str:
    """Search and return all file names found in the passed directory by a
    recursive search. The return format is a formatted string with each
    file's absolute path on a new line with a limit of 50. Example:
    list_files('.', '*.py'). '.venv', '.git' and '__pycache__' directories are
    ignored during search. If a list exceeds 50 lines, it is truncated and a
    message gives the total count; use a more specific pattern.

    Args:
        directory (str): Directory to search in, absolute or relative to the
            repository root
        pattern (str): The pattern is matched against the file name only, not
            the path. Must be in glob format. Example: '*.py' or 'test_*'.
            'core/*.py' will not work.

    Raises:
        ToolError: In case of fail during code execution or an attempt to
        access outside of authorized directory.
    """

    complete_filepath = os.path.normpath(os.path.join(TESTBED_PATH, directory))
    if _check_path(complete_filepath):
        excluded: list[str] = []

        for i, name in enumerate(EXCLUDED_DIRS):
            excluded.append("-name")
            excluded.append(name)
            if i < len(EXCLUDED_DIRS) - 1:
                excluded.append("-o")

        cmd: list[str] = [
            "find",
            complete_filepath,
            "(",
            *excluded,
            ")",
            "-prune",
            "-o",
            "-type",
            "f",
            "-name",
            pattern,
            "-print"
        ]
        run_return: CompletedProcess[str] = _run(cmd=cmd)
        if run_return.returncode != 0:
            code = run_return.returncode
            raise ToolError("The tool execution failed with code"
                            f" {code}:\n{run_return.stderr}")
        if run_return.stdout == "":
            return f"No file matching {pattern} in {directory}"
        if run_return.stdout.count("\n") > 50:
            msg: str = "files shown, use a more specific pattern"
            return _truncate(run_return.stdout, 50, msg)
        return run_return.stdout
    else:
        raise ToolError(f"You cannot access outside of {TESTBED_PATH}")


if __name__ == "__main__":
    mcp.run(show_banner=False, log_level="WARNING")
