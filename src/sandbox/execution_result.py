from pydantic import BaseModel


class ExecutionResult(BaseModel):
    output: str
    timed_out: bool = False
    crashed: bool = False
    final_answer: str | None = None
