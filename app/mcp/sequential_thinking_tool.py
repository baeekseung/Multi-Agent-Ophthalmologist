from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, List, Any

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools


@asynccontextmanager
async def sequential_thinking_tools() -> AsyncIterator[List[Any]]:
    """
    Sequential Thinking MCP 서버에 stateful session으로 연결한 뒤
    LangChain/LangGraph에서 사용할 tools를 로드합니다.
    """
    client = MultiServerMCPClient(
        {
            "sequential-thinking": {
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
                # 필요 시 로깅 비활성화
                "env": {
                    "DISABLE_THOUGHT_LOGGING": "true",
                },
            }
        }
    )

    # Sequential Thinking은 여러 thought step을 이어갈 수 있으므로
    # stateless get_tools()보다 session() + load_mcp_tools()가 더 적합합니다.
    async with client.session("sequential-thinking") as session:
        tools = await load_mcp_tools(session)
        yield tools