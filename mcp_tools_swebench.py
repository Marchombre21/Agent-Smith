import subprocess
import os
from subprocess import CompletedProcess
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

mcp = FastMCP("mcp_tools_swebench")

TESTBED_PATH = os.environ.get("TESTBED_PATH")
CONTAINER_ID = os.environ.get("CONTAINER_ID")

if not TESTBED_PATH:
    raise ValueError("Missing TESTBED_PATH variable to launch MCP server.")


def _run(cmd: list[str]) -> CompletedProcess:
    if CONTAINER_ID:
        final_cmd = ["docker", "exec", "-w", TESTBED_PATH, CONTAINER_ID] + cmd
        final_cwd = None
    else:
        final_cmd = cmd
        final_cwd = TESTBED_PATH
    return subprocess.run(
        final_cmd, text=True, capture_output=True, cwd=final_cwd
    )


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
    complete_filepath = os.path.join(TESTBED_PATH, filepath)
    cmd: list[str] = [
        "sed",
        "-n",
        f"{start_line},{end_line}p",
        "--",
        complete_filepath,
    ]
    result = ""
    run_return = _run(cmd=cmd)
    if run_return.returncode != 0:
        code = run_return.returncode
        raise ToolError(
            f"The tool execution failed with code {code}:\n{run_return.stderr}"
        )
    response = run_return.stdout.splitlines()
    for number, line in enumerate(response, start=start_line):
        result += f"{number}: {line}\n"
    if result == "":
        return "No lines in range, file has fewer lines."
    return result


if __name__ == "__main__":
    mcp.run(show_banner=False, log_level="WARNING")
