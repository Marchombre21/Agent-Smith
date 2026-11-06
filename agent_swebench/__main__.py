"""Entry point of the SWE-bench agent:
``python -m agent_swebench --task-file ...``.

The clock is read before the CLI is imported: the import takes about two
seconds, and the moulinette counts them in the task's timeout.
"""

import sys
import time
from pathlib import Path

if __name__ == "__main__":
    started_at = time.monotonic()
    from src.cli.swebench_cli import SweBenchCli

    sys.exit(
        SweBenchCli.launch(Path("configs/agent_swebench.json"), started_at)
    )
