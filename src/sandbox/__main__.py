import json
import sys
import os
from typing import Literal
from json import JSONDecodeError
from argparse import ArgumentParser
from src.sandbox.sandbox import Sandbox
from src.models import SandboxConfig
from src.sandbox_port import SandboxError
from pydantic import ValidationError
from src.sandbox.errors import TemplateError
from src.sandbox.run_repl import run_repl


def main() -> None:
    """Entry point of the ``sandbox`` command.

    Runs the sandbox CLI and turns expected errors (config file,
    sandbox start) into a message on stderr with exit code 1.
    """
    try:
        _run()
    except (OSError, TemplateError, SandboxError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def load_config(path: str | None) -> SandboxConfig:
    """Load the sandbox config from a JSON file, or defaults if no path."""
    if path is None:
        return SandboxConfig()
    with open(path, "r") as f:
        try:
            data = json.load(f)
        except JSONDecodeError as e:
            raise TemplateError(f"{path} is not a valid JSON:\n{e}") from e
    try:
        return SandboxConfig.model_validate(data)
    except ValidationError as e:
        raise TemplateError(f"Invalid sandbox config in {path}:\n{e}") from e


def _run() -> None:
    """Parse the command line, then run the REPL in a sandbox.

    The sandbox is configured from the JSON file given as argument, or
    with the default config if there is none. It is always closed at
    the end, including on Ctrl+C.

    Raises:
        OSError: If the config file cannot be read.
        TemplateError: If the config file is not a valid config.
        SandboxError: If the sandbox cannot be started.
    """
    parser = ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    parser.add_argument(
        "sand_template",
        help="JSON file for sandbox configuration",
        nargs="?",
        default=None,
    )
    group.add_argument(
        "--mcp-stdio",
        help="command line to launch mcp_tools (mbpp or swebench) file",
        type=str,
    )
    group.add_argument("--mcp-server", help="URL toward mcp server", type=str)
    args = parser.parse_args()

    transport: Literal['stdio', 'http'] | None = None
    address: str | None = None

    if args.mcp_server:
        transport, address = "http", args.mcp_server

    if args.mcp_stdio:
        transport, address = "stdio", args.mcp_stdio
    config: SandboxConfig = load_config(args.sand_template)

    env = {}
    env_vars = ["TESTBED_PATH", "CONTAINER_ID"]

    for var in env_vars:
        temp_var = os.environ.get(var)
        if temp_var:
            env[var] = temp_var

    with Sandbox(config=config, transport=transport,
                 address=address, env=env) as sandbox:
        try:
            run_repl(sandbox)
        except KeyboardInterrupt:
            print()


if __name__ == "__main__":
    main()
