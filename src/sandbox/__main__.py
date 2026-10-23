import json
import sys
from json import JSONDecodeError
from argparse import ArgumentParser
from src.sandbox.sandbox import Sandbox
from src.sandbox.ConfigSandbox import SandboxConfig
from pydantic import ValidationError
from src.sandbox.errors import TemplateError
from src.sandbox.run_repl import run_repl


def main() -> None:
    try:
        _run()
    except (OSError, TemplateError) as e:
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
    parser = ArgumentParser()
    parser.add_argument(
        "sand_template",
        help="JSON file for sandbox configuration",
        nargs="?",
        default=None,
    )
    parser.add_argument(
        "--mcp-stdio",
        help="command line to launch mcp_tools (mbpp or swebench) file",
        type=str,
    )
    parser.add_argument("--mcp-server", help="URL toward mcp server", type=str)
    args = parser.parse_args()
    config: SandboxConfig = load_config(args.sand_template)

    with Sandbox(config=config) as sandbox:
        run_repl(sandbox)


if __name__ == "__main__":
    main()
