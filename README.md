*This project has been created as part of the 42 curriculum by qdecross, bfitte.*

# Description

This project asks us to build an agentic framework capable of autonomously solving coding challenges.
Our agent will reason, write code, execute it in a sandboxed environment, and iterate
until a solution is found.

# Instructions

**Makefile commands:**

  ``make install``     - Install dependencies

  ``make run``         - Run the sandbox CLI without MCP server

  ``make run-stdio-mbpp``   - Run the sandbox CLI with MBPP MCP server over stdio. make run-stdio-mbpp [CONFIG=...] [MCP_MBPP_CMD=...]

  ``make run-stdio-swebench``   - Run the sandbox CLI with SWE-BENCH MCP server over stdio. make run-stdio-swebench [CONFIG=...] [MCP_SWE_CMD=...]

  ``make run-server``  - Run the sandbox CLI with MCP server over HTTP. If you keep the default value for MCP_URL, you must first run **make serve-http** to start an MCP server over HTTP. make run-server [CONFIG=...] [MCP_URL=...]

  ``make serve-http``       - Run the MBPP MCP server over HTTP on localhost:8000.

  ``make clean``       - Clean temporary files

  ``make clean-all``   - Clean virtual environment and temporary files

  ``make lint``        - Run linters and type checkers

  ``make lint-strict`` - Run linters and type checkers in strict mode

**Manual instructions:**

``uv sync`` - Installation (make install)

``uv run sandbox`` - Just sandbox, without MCP server (make run)

``uv run sandbox configs/sandbox_template.json``      - With personal configuration

``uv run sandbox --mcp-stdio "python3 mcp_tools_mbpp.py" <your config path>`` - Sandbox + MBPP MCP server over stdio (make run-stdio-mbpp)

``TESTBED_PATH=<repository path> uv run sandbox --mcp-stdio "python3 mcp_tools_swebench.py" <your config path>`` - Sandbox + SWE-BENCH MCP server over stdio (make run-stdio-swebench)

**TESTBED_PATH** (required by the SWE-bench server): root of the repository the tools work on. Every path given to a tool must stay inside it, and commands are run from it.

``uv run fastmcp run mcp_tools_mbpp.py --transport http --port 8000`` - MBPP MCP server over HTTP in a terminal (make serve-http)

``uv run sandbox --mcp-server http://localhost:8000/mcp configs/sandbox_template.json`` - Sandbox connected to this server in another terminal (make run-server)

<!-- # Tool implementation details

## MBPP Tools

### run_tests

This tool runs a candidate solution against a list of test assertions.

It takes the code and the list of asserts, then returns a JSON string {success, message, output}.

Each test is executed in a new **subprocess** to prevent the server from crashing if the code crashes (or if a `sys.exit()` is called, for example).

**sys.executable** is used instead of python3 so the tests run with the exact interpreter (and environment) that runs the server, whatever the PATH contains.

Looping through all the tests lets you know exactly which test failed.

## SWE-Bench Tools

### Common helpers

**_run:** Executes the command specified by the called tool in a subprocess. The command is a list of arguments passed to the subprocess without a shell, so no shell injection is possible. It also checks whether the process is running in a Docker container or locally. It adjusts the arguments accordingly.

**_resolve_path:** This function is called whenever a folder/file path is passed as an argument. It verifies that the target is inside TESTBED_PATH. Returns the absolute normalized path, or raise ToolError if outside.

**_truncate:** It allows you to truncate the tool's response in the event of a very long response (more than 50 lines). It adds a message to the response to notify the LLM that the response has been truncated. -->

# Tool implementation details

## MBPP tools

### `run_tests(code, test_list)`

Runs a candidate solution against the task's assertions and returns a JSON string `{"success", "message", "output"}`.

- **One subprocess per test**: `code + test` is run with `sys.executable -c`. A crash, a `sys.exit()` or an infinite loop in the candidate code cannot take the server down, and tests cannot affect each other.
- **`sys.executable`** instead of `python3`: the tests run with the exact interpreter (and environment) that runs the server, whatever the `PATH` contains.
- **Stops at the first failure** and returns the failing assert with its stderr (the traceback), which is what the LLM needs to fix its code. Any non-zero exit code counts as a failure (assertion, exception, syntax error).
- **5-second timeout per test**: the slowest MBPP reference test takes ~1.8 s (measured on the 1324 tests of the dataset), so a correct but slow solution is not rejected, while an infinite loop costs only 5 s of the 120 s task budget.
- An empty `test_list` returns `success: false` instead of a false "all tests passed".

## SWE-bench tools

### Common design

- **Local or container mode**: every command goes through `_run`. If `CONTAINER_ID` is set, it is run with `docker exec -i -w <workdir> <container>`; otherwise it is run on the host with `cwd=TESTBED_PATH`. The sandbox stays on the host, only the tool commands run in the container.
- **No shell**: commands are built as argument lists, so LLM input (a pattern, a path) is never interpreted as shell syntax (`;`, `>`, `$(...)`). Only `run_command` uses `bash -c`, on purpose.
- **stdin is never inherited**: `_run` always sends an input (empty by default). Otherwise the child process would read the server's stdin, which is the MCP JSON-RPC pipe.
- **Paths confined to the repository** (`_resolve_path`): every path is joined to `TESTBED_PATH` and normalized (`..` removed). If the result is outside `TESTBED_PATH`, a `ToolError` is raised. Paths starting with `/testbed` (the path the LLM sees in the prompt) are translated to `TESTBED_PATH`, so the same prompt works in local mode.
- **Truncation**: long outputs are cut to a fixed number of lines with a marker giving the total (`[Truncated: 50 of 312 ...]`), so the LLM knows something is missing and can refine its request. Search tools keep the beginning; `run_command` and `run_tests` keep the end, because errors and test summaries are at the end.
- **Errors**: invalid arguments, or a command that fails unexpectedly, raise a `ToolError`, which the LLM receives as an exception in the sandbox. "Nothing found" is not an error: an explicit message is returned.
- **Text only**: every tool returns a string (see *Sandbox design* for why). `run_command` and `run_tests` use `--- exit_code ---`, `--- stdout ---`, `--- stderr ---` sections.
- `.venv`, `.git` and `__pycache__` are ignored by all search tools.

### `read_file(filepath, start_line, end_line)`

Returns the requested lines (1-based, inclusive) prefixed with their number (`12: line content`), using `sed -n 'start,endp'`. An out-of-range request returns a message instead of an empty string.

### `list_files(directory, pattern)`

Recursive search with `find`, `pattern` being a glob matched against the file name (`*.py`, `test_*`). Ignored directories are skipped with `-prune`, so `find` does not even enter them. Limited to 50 results.

### `search_code(pattern, file_pattern)`

Literal text search with `grep -rnFI` (`-F`: no regex, so special characters in the LLM's pattern have no effect; `-I`: binary files skipped). `file_pattern` restricts the files (empty means all files). Results are formatted as `path:line content`, limited to 50 lines.

### `edit_file(filepath, old_str, new_str)`

Replaces an exact string, which must appear **exactly once**: the file is read, the replacement is done in Python with `str.replace`, and the new content is written back with `tee` (through stdin, so no quoting problem). `sed` was dropped because it interprets regex and special characters and does not handle multi-line replacements.
- 0 occurrences → error. Several occurrences → error listing the lines where they are, so the LLM can add context to make `old_str` unique.
- For `.py` files, the result is checked with `compile()`; if the edit introduces a syntax error, the old content is restored and the error is reported.

### `search_function_or_class_definition_in_code(name)`

Finds `def`, `async def` and `class` lines for an exact name with `grep -rnE` on `.py` files (`\b` so that `foo` does not match `foobar`). `name` must be a valid Python identifier, which also prevents injecting regex syntax.

### `find_references(name, filepath, line)`

First checks that `name` really appears at `line` in `filepath`, then lists every whole-word occurrence with `grep -rnwF` on `.py` files. The search is **textual**: comments, strings and other symbols with the same name are also returned (a semantic tool like `jedi` would be more precise, at the cost of a dependency in the container). Limited to 50 lines.

### `get_patch()`

Returns `git diff` of the repository: this is the patch submitted as the solution, so it is **never truncated**. `core.fileMode=false` ignores permission changes, which would pollute the patch. New untracked files are not included (assumed choice: the patch should only modify existing code).

### `run_command(command, workdir=".")`

Runs an arbitrary shell command chosen by the LLM with `bash -c`, from `workdir` (confined to the repository).
- Wrapped in `timeout -s KILL 60`: the timeout is applied **inside** the command, because a Python-side timeout would only kill the `docker exec` client, not the command running in the container. `KILL` cannot be ignored by the command; exit code 137 adds an explicit timeout message.
- This tool is not covered by the sandbox timeout (MCP calls happen outside the sandbox), so it needs its own.
- stdout and stderr keep their last 50 lines.

### `run_tests()`

Runs the task's official evaluation script, whose path is given by `SCRIPT_PATHS` (a file on the host, outside the repository, so the LLM cannot read the hidden tests). The script is sent to `bash -s` through stdin (no argument size limit).
- **The exit code is meaningless**: the script does not use `set -e`, so it returns 0 even if tests fail. The LLM must read the test summary at the end of stdout, which is why the outputs keep their last 100 lines.
- **Timeout of 100 s** with repository restoration: the script applies the hidden test files before running them. If it is killed, they would stay in the repository and end up in the patch. So the agent's changes are saved (`git diff --binary`) before running, and on timeout the repository is reset (`git checkout HEAD -- .`) and the saved changes re-applied (`git apply`). Any failure of this restoration is reported in stderr.



## Sandbox design

### Separate process

The code runs in a separate worker process. This is what makes the limits enforceable: on timeout the worker is killed with SIGKILL (an exception raised inside the same process could be caught by the code), the memory limit (RLIMIT_AS) only applies to the worker, and a crash only kills the worker, which is then restarted. Restricted builtins and imports are a first layer; if the code escapes them, it only reaches the worker, not the agent (API keys, MCP client).

### Parent/worker protocol



### SWE-Bench

All tools return plain text ; run_command/run_tests use --- exit_code/stdout/stderr --- sections to keep it consistent

# Resources
- [MCP Servers](https://www.stephane-robert.info/docs/developper/programmation/python/mcp/)
