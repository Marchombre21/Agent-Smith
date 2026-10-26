"""The trace of one task, in the format the subject imposes."""

from typing import List, Literal, Optional

from src.llm.models import LLMResponse
from src.models import SolutionOutput, StepMetrics


class StepRecorder:
    """Write one ``StepMetrics`` per step, then the ``SolutionOutput``.

    A step is one successful LLM call and at most one execution. Its
    metrics are created when the step ends, so their timestamps grow
    from one step to the next, as ``display`` checks.
    """

    # display warns about an empty llm_output; same text as Conversation.
    _EMPTY_ANSWER = "(empty answer)"

    def __init__(
        self,
        task_id: str,
        benchmark: Literal["mbpp", "swebench"],
        api_url: str,
        model_name: str,
    ) -> None:
        """Start a trace with no step.

        Args:
            task_id: Identifier of the task, as a string.
            benchmark: Which benchmark the task comes from.
            api_url: Provider URL given to the CLI; the same on every
                step.
            model_name: Model given to the CLI; the same on every step,
                as ``display`` warns about several models in one task.
        """
        self._task_id = task_id
        self._benchmark = benchmark
        self._api_url = api_url
        self._model_name = model_name
        self._steps: List[StepMetrics] = []

    def record(
        self,
        response: LLMResponse,
        code: Optional[str],
        observation: str,
    ) -> StepMetrics:
        """Record the step that has just ended and return its metrics.

        Args:
            response: The LLM answer of the step.
            code: Code sent to the sandbox; None when nothing was run.
            observation: Text sent back to the LLM. Not recorded when
                nothing was run: ``sandbox_output`` is the result of an
                execution, and ``display`` warns about an output with no
                input.
        """
        metrics = StepMetrics(
            step=len(self._steps) + 1,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            request_time_ms=response.request_time_ms,
            api_url=self._api_url,
            model_name=self._model_name,
            llm_output=response.text or self._EMPTY_ANSWER,
            sandbox_input=code if code is not None else "",
            sandbox_output=observation if code is not None else "",
            retries=response.retries,
        )
        self._steps.append(metrics)
        return metrics

    def finish(
        self,
        success: bool,
        solution: str,
        system_prompt: str,
        total_time_seconds: float,
        error: Optional[str] = None,
    ) -> SolutionOutput:
        """Build the output of the task from the steps recorded.

        Totals are computed from the steps themselves, so the output is
        consistent with its ``steps`` whatever happened in the loop.

        Args:
            success: Whether the agent believes it solved the task.
            solution: MBPP function code, or SWE-bench patch; may be
                empty when the task failed.
            system_prompt: Full system prompt sent to the LLM.
            total_time_seconds: Time since the process started.
            error: Why the task stopped without success; None otherwise.
        """
        return SolutionOutput(
            task_id=self._task_id,
            benchmark=self._benchmark,
            success=success,
            solution=solution,
            iterations=len(self._steps),
            # Each step is one successful request plus its failed tries.
            total_requests=sum(1 + s.retries for s in self._steps),
            total_input_tokens=sum(s.input_tokens for s in self._steps),
            total_output_tokens=sum(s.output_tokens for s in self._steps),
            total_time_seconds=total_time_seconds,
            steps=list(self._steps),
            system_prompt=system_prompt,
            error=error,
        )
