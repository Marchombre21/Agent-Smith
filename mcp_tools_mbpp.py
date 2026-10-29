import subprocess
import sys
import json
from subprocess import TimeoutExpired
from fastmcp import FastMCP

mcp = FastMCP("mcp_tools_mbpp")


@mcp.tool()
def run_tests(code: str, test_list: list[str]) -> str:
    '''
    Execute passed code and test assertions with the result. The function
    returns a json formatted string with success True/False, a message and an
    output.

    Args:
        code (str): The code to execute.
        test_list (list[str]): List of tests the result code is tested with.
    '''
    if len(test_list) == 0:
        return json.dumps(
            {
                "success": False,
                "message": "Missing tests",
                "output": "",
            }
        )
    for test in test_list:
        try:
            full_code = code + "\n" + test + "\n"
            result_test = subprocess.run([sys.executable, "-c", full_code],
                                         capture_output=True,
                                         text=True,
                                         timeout=3)
        except TimeoutExpired:
            result = {
                "success": False,
                "message": f"Timeout error with test {test}",
                "output": "Timeout after 3s.",
            }
            return json.dumps(result)

        if result_test.returncode != 0:

            result = {
                "success": False,
                "message": "Tests failed",
                "output": f"Failed test: {test}\n{result_test.stderr}",
            }
            return json.dumps(result)

    result = {
        "success": True,
        "message": "All tests passed!",
        "output": "",
    }
    return json.dumps(result)


if __name__ == "__main__":
    mcp.run(show_banner=False)
