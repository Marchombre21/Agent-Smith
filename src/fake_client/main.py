import asyncio
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    params = StdioServerParameters(command=sys.executable,
                                   args=["mcp_tools_mbpp.py"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("Tools :", [t.name for t in tools.tools])
            res = await session.call_tool(
                "run_tests", {
                    "code": "def add(a, b):\n    return a + b",
                    "test_list": ["assert add(1, 2) == 3"]
                })
            print("answer ->", [c for c in res.content])


asyncio.run(main())
