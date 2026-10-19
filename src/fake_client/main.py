import asyncio
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    params = StdioServerParameters(command=sys.executable,
                                   args=["src/mcp/__main__.py"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("Tools :", [t.name for t in tools.tools])
            res = await session.call_tool("search_notes",
                                          {"query": "test3"})
            print("search_notes ->", [c.text for c in res.content])


asyncio.run(main())
