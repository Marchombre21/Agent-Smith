# Tool implementation details

## Run_tests

This tool runs a candidate solution against a list of test assertions.

**Arguments**:

1. code (str): The code to execute.
2. test_list (list[str]): List of tests the result code is tested with.

**Return**: A json formatted string with success True/False, a message and an output if tests failed.

**Possible errors**:

- Empty list
- Timeout (>3s)
- Assertion Error

**subprocess** to prevent the server from crashing if the code crashes (or if a `sys.exit()` is called, for example).

**sys.executable** to have the same interpreter as the server

**stdio**: 

- Server launched by client on the same host
- When connection stops, the server too
- They communicate by stdout and stdin

TODO: Rajouter explication 1 process par test, les 3s, un exemple de réponse.

# Resources
- [MCP Servers](https://www.stephane-robert.info/docs/developper/programmation/python/mcp/)
