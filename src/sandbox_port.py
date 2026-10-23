"""The boundary between the agent loop and the sandbox.

The orchestrator only knows the sandbox through this module, so that it
does not depend on how the sandbox is built: the real sandbox and the
fakes used for testing both speak these terms.
"""

from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ExecutionResult(BaseModel):
    """What happened when one piece of code was executed.

    Raw facts only, with no sentence meant for the LLM: turning them into
    an observation is the orchestrator's job. Every flag defaults to
    False, so a plain successful run is ``ExecutionResult(stdout=...)``.
    """

    model_config = ConfigDict(frozen=True)

    # Ces champs sont une première proposition : ils peuvent encore
    # changer selon ce que la sandbox pourra réellement fournir.

    stdout: str = Field(
        default="", description="What the code printed, possibly truncated"
    )
    error: Optional[str] = Field(
        default=None,
        description="Formatted traceback of the exception the code raised; "
        "None when it ran to the end",
    )
    timed_out: bool = Field(
        default=False,
        description="The code was stopped by the execution time limit",
    )
    memory_exceeded: bool = Field(
        default=False, description="The code was stopped by the memory limit"
    )
    truncated: bool = Field(
        default=False,
        description="stdout was cut because it was too long",
    )
    state_reset: bool = Field(
        default=False,
        description="Variables from previous executions were lost, e.g. "
        "because the process running the code was killed",
    )
    final_answer: Optional[str] = Field(
        default=None,
        description="Value passed to final_answer(), converted with str(); "
        "None when final_answer() was not called",
    )


# Proposition : le nom
# et la place de cette exception peuvent changer.
class SandboxError(Exception):
    """The sandbox itself failed, so the code could not be run at all.

    For example the MCP server died, or the process that runs the code
    could not be reached. Errors of the LLM's code are not this: they are
    reported in ``ExecutionResult.error``.
    """


class SandboxPort(ABC):
    """A place where the LLM's code can run, as the orchestrator sees it.

    The real sandbox inherits from this class, and so do the fakes used
    for testing. Creating and closing the sandbox (processes, MCP
    connection, container) is left to whoever builds it: the
    orchestrator receives one ready to use and only runs code in it.
    """

    @abstractmethod
    def execute(
        self, code: str, timeout: Optional[float] = None
    ) -> ExecutionResult:
        """Run ``code`` and report what happened.

        Variables defined by earlier calls are still available, unless
        the result says ``state_reset``.

        Args:
            code: Python source written by the LLM.
            timeout: Seconds allowed for this run, when the task has less
                time left than the sandbox's own limit; None means the
                limit of the sandbox configuration.

        Returns:
            The result; errors of ``code`` itself, including a timeout,
            are reported in it and never raised.

        Raises:
            SandboxError: The sandbox itself is out of order.
        """

    # Point encore ouvert : le sujet impose un manuel généré depuis les
    # schémas des outils MCP, pas cette méthode. Son nom, et le choix
    # entre une sandbox qui écrit le texte ou qui expose seulement les
    # schémas, dépendent de la construction de la sandbox.
    @abstractmethod
    def manual(self) -> str:
        """Describe the tools available to the code, for the LLM.

        The text is inserted as is in the system prompt; it is generated
        from the schemas of the connected MCP server.
        """
