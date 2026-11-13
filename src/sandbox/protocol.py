import json
import time

from json import JSONDecodeError
from src.sandbox.errors import ProtocolError
from typing import Any, Callable, IO

AUTHORIZED_KEYS: dict[str, dict[str, Any]] = {
    "exec_stdout": {"exec_stdout": str},
    "tool_call": {"tool_call": str, "args": list, "kwargs": dict},
    "resource_call": {"resource_call": str},
}

FINAL_KEYS: dict[str, Any] = {
    "error": (str, type(None)),
    "memory_exceeded": bool,
    "answer": (str, type(None)),
    "interrupt": (str, type(None)),
    "exit_code": (int, type(None)),
}


def check_protocol(msg: str) -> dict[str, Any]:
    """Check if the returned message complies with the established
    communication protocol.

    Args:
        msg (str): The returned message

    Raises:
        ProtocolError: If msg is not JSON, not a dict, or does not match
        any message schema.

    Returns:
        dict[str, Any]: The returned message loaded as a dict.
    """
    error_msg: str = (
        "The received execution output is malformed. Protocol not"
        " followed. Cannot accept it"
    )
    try:
        message = json.loads(msg)
    except JSONDecodeError:
        raise ProtocolError(f"{error_msg}.")
    if not isinstance(message, dict):
        raise ProtocolError(f"{error_msg}.")

    for key in AUTHORIZED_KEYS:
        if key in message:
            schema = AUTHORIZED_KEYS[key]
            break
    else:
        schema = FINAL_KEYS

    for sch_key in schema:
        if sch_key not in message or not isinstance(
            message[sch_key], schema[sch_key]
        ):
            raise ProtocolError(f"{error_msg}.")

    return message


def server_call(
    limit: float,
    function: Callable[..., dict[str, Any]],
    stdin: IO[str],
    answer: dict[str, Any],
) -> float:
    start = time.monotonic()
    response = function(request=answer)
    stdin.write(json.dumps(response) + "\n")
    stdin.flush()
    limit += time.monotonic() - start
    return limit
