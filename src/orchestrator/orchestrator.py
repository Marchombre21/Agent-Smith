"""The agent loop: Thought -> Code -> Observation, until an answer."""

from typing import Optional

from src.extraction.chain import CodeExtraction
from src.llm.client import LLMClient
from src.llm.errors import LLMError
from src.orchestrator.budget import TaskBudget
from src.orchestrator.conversation import Conversation
from src.orchestrator.models import RunResult
from src.orchestrator.observation import ObservationFormatter
from src.orchestrator.recorder import StepRecorder
from src.sandbox_port import ExecutionResult, SandboxError, SandboxPort


class Orchestrator:
    """Run one task: call the LLM, run its code, feed the result back.

    It computes almost nothing itself: each part of a step is done by an
    object given to the constructor, so each one can be replaced by a
    fake in tests. It is the same for both benchmarks; what differs (the
    prompt, the tools, how the solution is built) is decided by the CLI.
    """

    # The model stops before writing an observation itself: the end of a
    # Python block, of a Hermes tool call, or a ReAct "Observation:".
    _STOP_SEQUENCES = ("<end_code>", "</tool_call>", "Observation:")

    def __init__(
        self,
        llm: LLMClient,
        sandbox: SandboxPort,
        extraction: CodeExtraction,
        formatter: ObservationFormatter,
        conversation: Conversation,
        budget: TaskBudget,
        recorder: StepRecorder,
    ) -> None:
        """Keep the parts of the loop.

        Args:
            llm: Sends the conversation, returns the model's answer.
            sandbox: Runs the code found in an answer.
            extraction: Finds the code in an answer.
            formatter: Turns a run into the text the model reads.
            conversation: Already holds the system prompt and the task.
            budget: Limits of the task, with the clock already started.
            recorder: Keeps the metrics of each step; the CLI reads it
                afterwards to write ``solution.json``.
        """
        self._llm = llm
        self._sandbox = sandbox
        self._extraction = extraction
        self._formatter = formatter
        self._conversation = conversation
        self._budget = budget
        self._recorder = recorder

    def run(self) -> RunResult:
        """Loop over steps until an answer, a limit or a failure.

        Before each step, the budget says whether the task may go on and
        whether the next call fits in the input tokens left. The loop
        always ends: ``stop_reason()`` stops it at the iteration limit.

        Returns:
            The answer, or why there is none. Only LLM and sandbox
            failures are caught here; anything else is a bug and goes up
            to the CLI.
        """
        while True:
            reason = self._budget.stop_reason()
            if reason is not None:
                return RunResult(error=reason)
            estimated = self._conversation.estimate_input_tokens()
            if not self._budget.can_afford(estimated):
                return RunResult(
                    error=f"input token limit would be exceeded "
                    f"(next call estimated at {estimated}, "
                    f"{self._budget.remaining_input_tokens} left)"
                )
            try:
                answer = self._step()
            except LLMError as error:
                return RunResult(error=f"LLM failure: {error}")
            except SandboxError as error:
                return RunResult(error=f"Sandbox failure: {error}")
            if answer is not None:
                return RunResult(final_answer=answer)

    def _step(self) -> Optional[str]:
        """Do one step: ask the LLM, run its code, feed the result back.

        The budget is checked by ``run()`` before calling this.

        Returns:
            The value passed to ``final_answer()``, or None to go on.

        Raises:
            LLMError: The LLM gave no answer (tries used up, time over).
            SandboxError: The sandbox itself broke; the step is recorded
                first, so its tokens appear in the trace.
        """
        response = self._llm.complete(
            self._conversation.messages,
            stop=self._STOP_SEQUENCES,
            max_tokens=self._budget.remaining_output_tokens,
            timeout=self._budget.remaining_seconds,
        )
        self._budget.record_step(response.input_tokens, response.output_tokens)
        self._conversation.add_answer(response.text)
        extracted = self._extraction.extract(response.text)
        result: Optional[ExecutionResult] = None
        if extracted.code is not None:
            try:
                result = self._sandbox.execute(
                    extracted.code, timeout=self._budget.remaining_seconds
                )
            except SandboxError as error:
                self._recorder.record(
                    response, extracted.code, f"Sandbox failure: {error}"
                )
                raise
        observation = self._formatter.format(extracted, result)
        self._conversation.add_observation(observation)
        self._recorder.record(response, extracted.code, observation)
        return result.final_answer if result is not None else None
