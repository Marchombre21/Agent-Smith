"""Entry point of the MBPP agent: ``python -m agent_mbpp --task-file ...``.

The clock is read before the CLI is imported: the import takes about two
seconds, and the moulinette counts them in the task's timeout.
"""

import sys
import time
from pathlib import Path

if __name__ == "__main__":
    started_at = time.monotonic()
    from src.cli.mbpp_cli import MbppCli

    sys.exit(MbppCli.launch(Path("configs/agent_mbpp.json"), started_at))
