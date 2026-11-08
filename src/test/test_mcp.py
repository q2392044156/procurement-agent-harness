"""MCP Server 连接测试（透传内部令牌，走真实平台）。

用法：conda run -n procurement python src/test/test_mcp.py
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.env_utils import load_env

load_env()

MCP_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8001")
TOKEN = os.getenv("AGENT_INTERNAL_TOKEN", "")
USER_ID = os.getenv("AGENT_TEST_USER_ID", "1")


def parse_result(raw) -> dict:
    """兼容 dict / [{"type":"text","text":...}] / JSON 字符串。"""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        text = "".join(
            item.get("text", "") if isinstance(item, dict) else str(item) for item in raw
        )
    else:
        text = str(raw)
    start = text.find("{")
    if start < 0:
        return {}
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        return {}


async def main() -> int:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    if not TOKEN:
        print("FAIL: AGENT_INTERNAL_TOKEN 未配置")
        return 1

    print(f"[1] 连接 MCP Server: {MCP_URL}/sse")
    client = MultiServerMCPClient(
        {
            "erp": {
                "url": f"{MCP_URL}/sse",
                "transport": "sse",
                "headers": {
                    "X-Internal-Token": TOKEN,
                    "X-User-Id": USER_ID,
                    "X-Request-Id": "test-mcp",
                },
            }
        }
    )

    tools = await client.get_tools()
    print(f"[2] 获取到 {len(tools)} 个工具")
    by_name = {tool.name: tool for tool in tools}

    cases = [
        ("supplier_page", {"current": 1, "size": 3}),
        ("part_page", {"current": 1, "size": 3}),
        ("inventory_warning", {}),
    ]
    failed = 0
    for name, args in cases:
        if name not in by_name:
            print(f"    {name}: MISSING")
            failed += 1
            continue
        data = parse_result(await by_name[name].ainvoke(args))
        ok = data.get("code") == 0
        print(f"    {name}: {'PASS' if ok else 'FAIL'} (code={data.get('code')})")
        if not ok:
            failed += 1

    print("\nMCP 测试完成" if not failed else f"\nMCP 测试失败: {failed}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
