"""What the command lines of both agents share: options, wiring, output."""

import argparse
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Literal, Optional, Sequence

import httpx
from pydantic import ValidationError

from src.cli.models import AgentSettings
from src.cli.task import BenchmarkTask
from src.extraction.chain import CodeExtraction
from src.llm.config import ProviderRegistry
from src.llm.rotating_client import RotatingClient
from src.models import SolutionOutput
from src.orchestrator.budget import TaskBudget
from src.orchestrator.conversation import Conversation
from src.orchestrator.models import TaskLimits
from src.orchestrator.observation import ObservationFormatter
from src.orchestrator.orchestrator import Orchestrator
from src.orchestrator.recorder import StepRecorder
from src.sandbox.sandbox import Sandbox


class BenchmarkCli(ABC):
    """Run one task of a benchmark from the command line.

    The options are the ones the subject imposes (``--task-file``,
    ``--output``, ``--model-name``, ``--provider-url``), the same for both
    benchmarks. The subclass says which benchmark it runs, how to read
    its task and which limits apply (template method pattern); the task
    itself (``BenchmarkTask``) knows its prompt and how to conclude.
    """

    _PROVIDERS_FILE = Path("configs/providers.json")

    def __init__(
        self,
        settings: AgentSettings,
        registry: ProviderRegistry,
        http: httpx.Client,
        started_at: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Keep what the run needs; nothing is started yet.

        Args:
            settings: Defaults of the agent (``configs/agent_*.json``).
            registry: The known providers.
            http: HTTP client for the LLM, owned and closed by the caller.
            started_at: Value of ``clock`` when the process started: the
                subject's timeout counts from there, not from the first
                LLM call.
            clock: Returns the current time in seconds.
        """
        self._settings = settings
        self._registry = registry
        self._http = http
        self._started_at = started_at
        self._clock = clock

    @classmethod
    def launch(
        cls,
        settings_path: Path,
        started_at: float,
        argv: Optional[Sequence[str]] = None,
    ) -> int:
        """Build the CLI from the configuration files and run it.

        Paths are relative to the current directory: the moulinette runs
        the agent from the root of the repository.

        Args:
            settings_path: Settings of this agent (``configs/agent_*.json``).
            started_at: ``time.monotonic()`` taken before the imports, by
                ``__main__`` (design C).
            argv: Options without the program name; None reads
                ``sys.argv``.

        Returns:
            The exit code of ``main``; 1 if the configuration cannot be
            loaded, since nothing can be solved without it.
        """
        try:
            settings = AgentSettings.from_file(settings_path)
            registry = ProviderRegistry.from_file(cls._PROVIDERS_FILE)
        except (OSError, ValidationError, ValueError) as error:
            print(f"cannot load the agent configuration: {error}",
                  file=sys.stderr)
            return 1
        with httpx.Client() as http:
            return cls(settings, registry, http, started_at).main(argv)

    def main(self, argv: Optional[Sequence[str]] = None) -> int:
        """Solve one task and write ``solution.json`` (design B).

        Args:
            argv: Options without the program name; None reads
                ``sys.argv``.

        Returns:
            0 once the file is written, whatever the outcome of the
            task; 1 if the file cannot be written, the only failure the
            moulinette must see.

        Raises:
            SystemExit: an option is missing or unknown (code 2, from
                argparse): without ``--output`` there is nowhere to write.
        """
        args = self._parse_args(argv)
        output = self._solve(args)
        try:
            self._write(output, args.output)
        except OSError as error:
            print(f"cannot write {args.output}: {error}", file=sys.stderr)
            return 1
        return 0

    def _parse_args(
        self, argv: Optional[Sequence[str]]
    ) -> argparse.Namespace:
        """Read the options imposed by the subject (V.3, V.4).

        Args:
            argv: Options without the program name; None reads
                ``sys.argv``.

        Raises:
            SystemExit: an option is missing or unknown (argparse prints
                the usage first).
        """
        parser = argparse.ArgumentParser(
            prog=f"python -m agent_{self._benchmark()}",
            description=f"Solve one {self._benchmark()} task.",
        )
        parser.add_argument("--task-file", required=True,
                            help="JSON file of the task")
        parser.add_argument("--output", required=True,
                            help="where to write solution.json")
        parser.add_argument("--model-name",
                            help="default: model_name of the settings")
        parser.add_argument("--provider-url",
                            help="default: URL of the settings' provider")
        return parser.parse_args(argv)

    def _resolve_model(self, args: argparse.Namespace) -> tuple[str, str]:
        """Choose the provider URL and the model of the run (design I).

        The command line wins; what it leaves out comes from the
        settings. The default model is only valid with the default
        provider: a model name means nothing to another provider.

        Args:
            args: The parsed options.

        Returns:
            ``(provider_url, model_name)``, ready for
            ``RotatingClient.from_provider_url``.

        Raises:
            KeyError: the settings name an unknown provider.
            ValueError: ``--provider-url`` names another provider than
                the default one, without ``--model-name``.
        """
        default = self._registry.get(self._settings.provider)
        url: Optional[str] = args.provider_url
        model: Optional[str] = args.model_name
        if model is None:
            if url is not None and not default.matches_url(url):
                raise ValueError(
                    f"--model-name is required with --provider-url {url}: "
                    f"the default model {self._settings.model_name!r} "
                    f"belongs to {default.name}"
                )
            model = self._settings.model_name
        return (url if url is not None else default.base_url), model

    def _solve(self, args: argparse.Namespace) -> SolutionOutput:
        """Solve the task given by ``args``, whatever happens (design B).

        Any failure (unreadable task, unknown provider, missing key,
        sandbox that does not start, bug) becomes an output with
        ``success=False`` and ``error``, so that ``solution.json`` is
        always written. The steps already recorded are kept.
        ``KeyboardInterrupt`` and ``SystemExit`` are not ``Exception``
        subclasses: they go through, as the subject requires.

        Args:
            args: The parsed options.

        Returns:
            The output to write; filled with what is known when the run
            failed early (an empty ``task_id`` if even the task could not
            be read).
        """
        task_id: str = ""
        url: str = args.provider_url or ""
        model: str = args.model_name or ""
        recorder: Optional[StepRecorder] = None
        try:
            task = self._load_task(args.task_file)
            task_id = task.task_id()
            url, model = self._resolve_model(args)
            recorder = StepRecorder(task_id, self._benchmark(), url, model)
            return self._run(task, url, model, recorder)
        except Exception as error:
            if recorder is None:
                recorder = StepRecorder(
                    task_id, self._benchmark(), url, model
                )
            return recorder.finish(
                success=False,
                solution="",
                system_prompt="",
                total_time_seconds=self._clock() - self._started_at,
                error=f"{type(error).__name__}: {error}",
            )

    def _run(
        self,
        task: BenchmarkTask,
        url: str,
        model: str,
        recorder: StepRecorder,
    ) -> SolutionOutput:
        """Wire the parts of the agent, run the loop and conclude.

        Nothing is caught here: ``_solve`` turns any failure into an
        output. The recorder comes from the caller, so that the steps
        already done are not lost when something fails.

        Args:
            task: The task to solve.
            url: Provider URL, from ``_resolve_model``.
            model: Model name, from ``_resolve_model``.
            recorder: Records each step; finished here.

        Raises:
            KeyError, ValueError: the client cannot be built (see
                ``RotatingClient.from_provider_url``).
            SandboxError: the sandbox or its MCP server cannot start.
        """
        budget = TaskBudget(self._limits(), self._started_at, self._clock)
        llm = RotatingClient.from_provider_url(
            url, model, self._registry, self._http
        )
        prompt = task.prompt()
        with self._open_sandbox() as sandbox:
            system_prompt = prompt.system_prompt(sandbox.manual())
            conversation = Conversation(
                system_prompt,
                prompt.task_message(),
                keep_last_observations=self._settings.keep_last_observations,
            )
            loop = Orchestrator(
                llm=llm,
                sandbox=sandbox,
                extraction=CodeExtraction.default(),
                formatter=ObservationFormatter(),
                conversation=conversation,
                budget=budget,
                recorder=recorder,
            )
            result = loop.run()
            success, solution = task.conclude(result, sandbox)
        return recorder.finish(
            success=success,
            solution=solution,
            system_prompt=system_prompt,
            total_time_seconds=budget.elapsed_seconds,
            error=result.error,
        )

    def _open_sandbox(self) -> Sandbox:
        """Build the sandbox described by the settings, not started yet.

        Use it in a ``with`` block: entering starts the worker and
        connects the MCP server, leaving stops both.
        """
        return Sandbox(
            self._settings.sandbox,
            self._settings.transport,
            self._settings.address,
        )

    @staticmethod
    def _write(output: SolutionOutput, path: str) -> None:
        """Write ``output`` as JSON to ``path`` (``--output``).

        The parent directories are created if needed: the moulinette
        gives a path, not the promise that its directory exists.

        Args:
            output: The output of the run, successful or not.
            path: Where to write ``solution.json``.

        Raises:
            OSError: the file cannot be written (``main`` turns it into
                a non-zero exit code, design B).
        """
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output.model_dump_json(indent=2), encoding="utf-8")

    @abstractmethod
    def _benchmark(self) -> Literal["mbpp", "swebench"]:
        """Return the name of the benchmark, as in ``solution.json``."""

    @abstractmethod
    def _load_task(self, path: str) -> BenchmarkTask:
        """Read the task given by ``--task-file``.

        Raises:
            OSError: the file cannot be read.
            pydantic.ValidationError: the file is not a valid task.
        """

    @abstractmethod
    def _limits(self) -> TaskLimits:
        """Return the limits of the task, from the settings."""
