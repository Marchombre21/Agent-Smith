import subprocess
import os
import re
from subprocess import CompletedProcess
from pathlib import Path
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

mcp = FastMCP("mcp_tools_swebench")

testbed_path_temp = os.environ.get("TESTBED_PATH", "")
CONTAINER_ID = os.environ.get("CONTAINER_ID")
SCRIPT_PATHS = os.environ.get("SCRIPT_PATHS")
EXCLUDED_DIRS = [".venv", ".git", "__pycache__"]
COMMAND_TIMEOUT = 60
TESTS_TIMEOUT = 100

if not testbed_path_temp:
    raise ValueError("Missing TESTBED_PATH variable to launch MCP server.")

TESTBED_PATH = os.path.abspath(testbed_path_temp)


def _resolve_path(path: str) -> str:
    """Return the absolute normalized path, or raise ToolError if outside."""

    complete_filepath = os.path.normpath(os.path.join(TESTBED_PATH, path))
    if not Path(complete_filepath).is_relative_to(TESTBED_PATH):
        raise ToolError(f"You cannot access outside of {TESTBED_PATH}")

    return complete_filepath


def _format_output(output: str) -> str:

    final_return: str = ""
    for line in output.splitlines():
        split_line = line.split(":", 2)
        final_return += f"{split_line[0]}:{split_line[1]} {split_line[2]}\n"
    return final_return


def _run(cmd: list[str],
         input: str = "",
         workdir: str = TESTBED_PATH) -> CompletedProcess[str]:
    if CONTAINER_ID:
        final_cmd = [
            "docker",
            "exec",
            "-i",
            "-w",
            workdir,
            CONTAINER_ID,
        ] + cmd
        final_cwd = None
    else:
        final_cmd = cmd
        final_cwd = workdir
    try:
        return subprocess.run(
            final_cmd,
            text=True,
            capture_output=True,
            cwd=final_cwd,
            input=input,
        )
    # Missing executable or cwd: subprocess raises instead of returning a
    # code. Mimic docker exec (code 127) so callers only check returncode.
    # (e.g. edit_file rollback)
    except FileNotFoundError as e:
        return CompletedProcess(final_cmd, 127, stderr=str(e), stdout="")


def _truncate(sentence: str, nb_lines: int, msg: str) -> str:
    tmp_datas: list[str] = sentence.splitlines()
    length_datas = len(tmp_datas)

    if length_datas <= nb_lines:
        return sentence

    final: str = f"\n[Truncated: {nb_lines} of {length_datas} {msg}]"
    new_data = "\n".join(tmp_datas[:nb_lines]) + final
    return new_data


def _truncate_by_end(sentence: str, nb_lines: int) -> str:
    tmp_datas: list[str] = sentence.splitlines()
    length_datas = len(tmp_datas)

    if length_datas <= nb_lines:
        return sentence

    final: str = f"[Truncated: {nb_lines} last lines of {length_datas}]\n"
    index: int = length_datas - nb_lines
    new_data = final + "\n".join(tmp_datas[index:])
    return new_data


def _return_error(code: int, err: str | None) -> None:
    if code != 0:
        raise ToolError("The tool execution failed with code"
                        f" {code}:\n{err}")


def _read_file(filepath: str, start_line: int, end_line: int) -> str:

    if start_line < 1:
        raise ToolError("The start_line value cannot be lower than 1.")
    if start_line > end_line:
        raise ToolError("The start_line cannot be greater than end_line.")
    complete_filepath: str = _resolve_path(filepath)
    cmd: list[str] = [
        "sed",
        "-n",
        f"{start_line},{end_line}p",
        "--",
        complete_filepath,
    ]
    run_return: CompletedProcess[str] = _run(cmd=cmd)
    _return_error(run_return.returncode, run_return.stderr)
    return run_return.stdout


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
        ToolError: If start_line is lower than 1 or greater than end_line.
        If the file cannot be read (e.g. it does not exist).
    """

    result = ""
    run_return: str = _read_file(filepath, start_line, end_line)
    response = run_return.splitlines()
    for number, line in enumerate(response, start=start_line):
        result += f"{number}: {line}\n"
    if result == "":
        return "No lines in range, file has fewer lines."
    return result


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

    complete_filepath: str = _resolve_path(directory)
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
        "-print",
    ]
    run_return: CompletedProcess[str] = _run(cmd=cmd)
    _return_error(run_return.returncode, run_return.stderr)
    if run_return.stdout == "":
        return f"No file matching {pattern} in {directory}"
    msg: str = "files shown, use a more specific pattern"
    return _truncate(run_return.stdout, 50, msg)


@mcp.tool()
def search_code(pattern: str, file_pattern: str) -> str:
    """Search a literal text in the repository files whose name matches
    file_pattern. The return is in format:
    /absolute/path_to_file.py:<line_number> <line_content>
    /absolute/path_to_other_file.py:<line_number> <line_content>
    ...
    '.venv', '.git' and '__pycache__' directories are
    ignored during search. If a list exceeds 50 lines, it is truncated and a
    message gives the total count; use a more specific pattern.

    Args:
        pattern (str): The searched pattern in code, literal text, not a regex.
        file_pattern (str):  Glob matched against file names only, not paths.
            Empty means all files. Must be in glob format.
            Example: '*.py' or 'test_*'. 'core/*.py' will not work.

    Raises:
        ToolError: In case of fail during code execution or an empty pattern.
    """

    if not pattern:
        raise ToolError("The pattern to search in code can't be empty or None")

    if not file_pattern:
        file_pattern = "*"

    excluded: list[str] = []

    for name in EXCLUDED_DIRS:
        excluded.append(f"--exclude-dir={name}")

    cmd: list[str] = [
        "grep",
        "-rnFI",
        *excluded,
        "-e",
        pattern,
        f"--include={file_pattern}",
        TESTBED_PATH,
    ]

    run_return: CompletedProcess[str] = _run(cmd=cmd)
    if run_return.returncode == 1:
        return (f"No code matching '{pattern}' in files matching"
                f" '{file_pattern}'.")
    _return_error(run_return.returncode, run_return.stderr)

    msg: str = "matching lines shown, use a more specific pattern"
    return _truncate(_format_output(run_return.stdout), 50, msg)


@mcp.tool()
def edit_file(filepath: str, old_str: str, new_str: str) -> str:
    """Replace an exact string in a file with a new string.

    old_str must appear exactly once in the file. For .py files, the
    result is checked for syntax errors: if the edit breaks the syntax,
    it is rejected, the file stays unchanged and the error is reported.
    Example:
    edit_file('src/module.py', 'return "An error occurs"',
    'raise ToolError("An error occurs")')
    Returns a confirmation message if the replacement succeeded.

    Args:
        filepath (str): Path of the file to edit, absolute or relative to
            the repository root.
        old_str (str): The exact text to replace. Must appear exactly once.
        new_str (str): The text that replaces old_str.

    Raises:
        ToolError: If filepath or old_str is empty, if old_str is not
            found or found more than once, if the edit introduces a
            syntax error in a .py file (file left unchanged), or if a
            command fails.
    """

    if not old_str or not filepath:
        raise ToolError("Args 'filepath' and 'old_str' can't be empty.")

    complete_filepath: str = _resolve_path(filepath)

    cmd: list[str] = ["cat", complete_filepath]

    run_return: CompletedProcess[str] = _run(cmd=cmd)
    _return_error(run_return.returncode, run_return.stderr)
    match run_return.stdout.count(old_str):
        case 0:
            raise ToolError("Old_str not found")
        case n if n > 1:
            raise ToolError("More than one occurrence. Be more specific.")
    old_content = run_return.stdout
    new_content = run_return.stdout.replace(old_str, new_str)
    cmd = ["tee", complete_filepath]
    run_return = _run(cmd=cmd, input=new_content)
    _return_error(run_return.returncode, run_return.stderr)
    if complete_filepath.endswith(".py"):
        code = ("import sys; compile(open(sys.argv[1]).read(),"
                " sys.argv[1], 'exec')")
        cmd = [
            "python",
            "-c",
            code,
            complete_filepath,
        ]
        run_return = _run(cmd=cmd)
        if run_return.returncode != 0:
            err = ("".join(run_return.stderr.splitlines(keepends=True)[2:])
                   or run_return.stderr)
            cmd = ["tee", complete_filepath]
            rollback = _run(cmd=cmd, input=old_content)
            state = ("file unchanged" if rollback.returncode == 0 else
                     "rollback FAILED, file contains the broken edit")
            raise ToolError(f"Edit rejected ({state}): {err}")
    return "Old_str replaced by new_str with success."


@mcp.tool()
def search_function_or_class_definition_in_code(name: str) -> str:
    """Find where a function or class is defined (def, async def or class).

    The name must match exactly (case-sensitive, 'foo' does not match
    'foobar'). Methods are included, so several definitions can be found:
    one line per definition, in this format:
    /absolute/path_to_file.py:<line_number> <line_content>
    Only the definition line is returned: use read_file to see the body.
    Only .py files are searched; .venv, .git and __pycache__ are ignored.
    If nothing is found, an explicit message is returned. Results are
    limited to 50 lines; if truncated, use search_code with more context
    (e.g. 'class MyClass') to narrow down.
    Example: search_function_or_class_definition_in_code('edit_file')
    It returns the matching definition lines, or a message if none is found.

    Args:
        name (str): Exact name of the function or class, without
            parentheses or module prefix. Must be a valid Python
            identifier (e.g. 'validate_email', not 'utils.validate_email').

    Raises:
        ToolError: If name is not a valid Python identifier, or if the
            search command fails.
    """

    if not name.isidentifier():
        raise ToolError("'name' must be a valid python identifier.")

    excluded: list[str] = []

    for name_dir in EXCLUDED_DIRS:
        excluded.append(f"--exclude-dir={name_dir}")

    regex = (
        rf"^[[:space:]]*(async[[:space:]]+)?(def|class)[[:space:]]+{name}\b")
    cmd = ["grep", "-rnE", regex, *excluded, "--include=*.py", TESTBED_PATH]

    run_return = _run(cmd=cmd)
    if run_return.returncode == 1:
        return "No definition found"
    _return_error(run_return.returncode, run_return.stderr)

    msg: str = "matching lines shown, use a more specific pattern"
    return _truncate(_format_output(run_return.stdout), 50, msg)


@mcp.tool()
def find_references(name: str, filepath: str, line: int) -> str:
    """Find all usages of a function or class in the repository.

    The symbol is first checked at the given location (usually its
    definition, found with search_function_or_class_definition_in_code):
    'name' must appear at 'line' in 'filepath', otherwise an error is
    raised. Then every whole-word occurrence of 'name' is returned, one
    line per occurrence, in this format:
    /absolute/path_to_file.py:<line_number> <line_content>
    The search is textual: the definition itself, comments, strings and
    other symbols with the same name are also returned.
    Only .py files are searched; .venv, .git and __pycache__ are ignored.
    If nothing is found, an explicit message is returned. Results are
    limited to 50 lines; if truncated, use search_code with more context
    (e.g. 'MyClass.method(') to narrow down.
    Example: find_references('validate_email', 'src/utils.py', 12)

    Args:
        name (str): Exact name of the function or class, without
            parentheses or module prefix. Must be a valid Python
            identifier (e.g. 'validate_email', not 'utils.validate_email').
        filepath (str): File where the symbol is located, absolute or
            relative to the repository root.
        line (int): Line number (starts at 1) where 'name' appears in
            filepath.

    Raises:
        ToolError: If name is not a valid Python identifier, if name is
            not found at line in filepath, if filepath is outside the
            repository, or if the search command fails.
    """

    if not name.isidentifier():
        raise ToolError("'name' must be a valid python identifier.")

    line_found: str = _read_file(filepath=filepath,
                                 start_line=line,
                                 end_line=line)

    if not re.search(rf"\b{name}\b", line_found):
        raise ToolError(f"{name} not found at line {line} in {filepath}")

    excluded: list[str] = []

    for name_dir in EXCLUDED_DIRS:
        excluded.append(f"--exclude-dir={name_dir}")

    cmd = ["grep", "-rnwFI", name, *excluded, "--include=*.py", TESTBED_PATH]

    run_return = _run(cmd=cmd)
    if run_return.returncode == 1:
        return "No occurrences found"
    _return_error(run_return.returncode, run_return.stderr)
    msg: str = "matching lines shown."
    return _truncate(_format_output(run_return.stdout), 50, msg)


@mcp.tool()
def get_patch() -> str:
    """Return the unified git diff of all changes made to the repository
    since the last commit (git -c core.fileMode=false diff).

    This diff is the patch that will be submitted as the solution: check
    it before giving your final answer. It is never truncated.
    Only modifications of tracked files are included: new untracked
    files (e.g. a reproduction script) do not appear in the patch.
    If nothing was modified, an explicit message is returned.

    Raises:
        ToolError: If the git command fails (e.g. not a git repository).
    """
    cmd = [
        "git",
        "-c",
        "core.fileMode=false",
        "diff",
    ]

    run_return = _run(cmd=cmd)
    _return_error(run_return.returncode, run_return.stderr)
    if run_return.stdout == "":
        return "No changes in the repository."
    return run_return.stdout


@mcp.tool()
def run_command(command: str, workdir: str = ".") -> dict[str, str | int]:
    """Execute a shell command in the targeted workdir. Return the result of
    the subprocess (stdout, stderr and exit_code) in dict format (
    {
    'stdout': <stdout>,
    'stderr': <stderr>,
    'exit_code': <return_code>,
    }).
    If stdout or stderr are too long, they will be truncated by the beginning
    and only the end of message will be returned.
    The execution has a timeout to ensure that no blockages can occur.

    Args:
        command (str): The shell command in a string
        workdir (str): Directory relative to the testbed (default: testbed
        root)
    """

    if not command.strip():
        raise ToolError("The argument 'command' can't be empty and must be"
                        " a valid command.")
    complete_path: str = _resolve_path(workdir)

    cmd = [
        "timeout", "-s", "KILL",
        str(COMMAND_TIMEOUT), "bash", "-c", command
    ]

    run_return = _run(cmd=cmd, workdir=complete_path)

    if run_return.returncode == 137:
        run_return.stderr += f"\n[Command killed after {COMMAND_TIMEOUT}s"\
                              " timeout]"

    return {
        "stdout": _truncate_by_end(run_return.stdout, 50),
        "stderr": _truncate_by_end(run_return.stderr, 50),
        "exit_code": run_return.returncode
    }


@mcp.tool()
def run_tests() -> dict[str, str | int]:
    """Run the evaluation script of the task (the official tests).

    Returns a dict with "stdout", "stderr" and "exit_code". The test
    results are in the summary at the end of "stdout": the exit code
    does NOT tell whether the tests passed (it is 0 even when some
    fail). Each output is truncated to its last 100 lines.

    The script is killed after 100 seconds. The state of the repository
    is saved before running it, so that it can be restored if the tests
    time out: your changes are kept and a message is added to "stderr".

    Raises:
        ToolError: If the evaluation script is missing or unreadable, or
            if the state of the repository cannot be saved.
    """
    if not SCRIPT_PATHS:
        raise ToolError("Missing SCRIPT_PATHS environment variable.")

    try:
        script: str = Path(SCRIPT_PATHS).read_text()
    except OSError as e:
        raise ToolError(f"Cannot read the evaluation script: {e}") from e
    if not script.strip():
        raise ToolError("No script provided.")

    cmd = ["git", "-c", "core.fileMode=false", "diff", "--binary"]

    diff_result = _run(cmd=cmd)
    _return_error(diff_result.returncode, diff_result.stderr)
    saved = diff_result.stdout

    cmd = ["timeout", "-s", "KILL", str(TESTS_TIMEOUT), "bash", "-s"]

    tests_results = _run(cmd=cmd, input=script)
    if tests_results.returncode == 137:
        tests_results.stderr += f"\n[Tests killed after {TESTS_TIMEOUT}s"\
                             " timeout.]"
        cmd = ["git", "checkout", "HEAD", "--", "."]
        restore_result = _run(cmd=cmd)
        if restore_result.returncode != 0:
            tests_results.stderr += "\n[Warning: could not restore the"\
                f" repository after timeout: {restore_result.stderr}]"
        if saved and restore_result.returncode == 0:
            restore_result = _run(["git", "apply"], input=saved)
            if restore_result.returncode != 0:
                tests_results.stderr += "\n[Warning: could not restore the"\
                    " repository after timeout, your changes are lost, apply"\
                    f" them again : {restore_result.stderr}]"

    return {
        "stdout": _truncate_by_end(tests_results.stdout, 100),
        "stderr": _truncate_by_end(tests_results.stderr, 100),
        "exit_code": tests_results.returncode
    }


if __name__ == "__main__":
    mcp.run(show_banner=False, log_level="WARNING")
