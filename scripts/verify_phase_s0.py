"""S0 阶段门禁：真机只读链路。

检查项：
1. 平台健康检查
2. 平台演示账号登录（拿到真实 user_id）
3. MCP Server 可达，工具数量与关键工具存在
4. supplier_page / part_page / inventory_warning 返回真实平台数据
5. 一次真实 LLM 调用

用法：conda run -n procurement python scripts/verify_phase_s0.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=True)

import httpx  # noqa: E402

PLATFORM = os.getenv("ERP_BASE_URL", "http://localhost:8080")
MCP_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8001")
TOKEN = os.getenv("AGENT_INTERNAL_TOKEN", "")

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    return ok


def login() -> tuple[str, str]:
    response = httpx.post(
        f"{PLATFORM}/api/v1/auth/login",
        json={"username": "admin", "password": "Admin@123"},
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()["data"]
    return str(data["user"]["id"]), str(data["accessToken"])


def parse_tool_result(raw) -> dict:
    """兼容三种返回形态：dict / [{'type':'text','text':...}] / JSON 字符串。"""
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
        if os.getenv("S0_DEBUG"):
            print("raw tool result:", repr(raw)[:500])
        return {}


async def main() -> int:
    check("internal token configured (>=32)", len(TOKEN) >= 32, f"len={len(TOKEN)}")

    try:
        health = httpx.get(f"{PLATFORM}/actuator/health", timeout=10)
        check("platform health", health.status_code == 200 and health.json().get("status") == "UP")
    except Exception as exc:  # noqa: BLE001
        check("platform health", False, str(exc)[:80])

    user_id, jwt = login()
    check("platform login", bool(user_id and jwt), f"user_id={user_id}")

    from langchain_mcp_adapters.client import MultiServerMCPClient  # noqa: E402

    client = MultiServerMCPClient(
        {
            "erp": {
                "url": f"{MCP_URL}/sse",
                "transport": "sse",
                "headers": {
                    "X-Internal-Token": TOKEN,
                    "X-User-Id": user_id,
                    "X-Request-Id": "s0-gate",
                },
            }
        }
    )
    tools = await client.get_tools()
    names = sorted(t.name for t in tools)
    check("mcp tools loaded", len(tools) >= 20, f"count={len(tools)}")
    required = {"supplier_page", "part_page", "inventory_warning"}
    check("required tools present", required.issubset(set(names)), ",".join(sorted(required - set(names))) or "ok")

    by_name = {t.name: t for t in tools}

    supplier = parse_tool_result(await by_name["supplier_page"].ainvoke({"current": 1, "size": 3}))
    supplier_ok = supplier.get("code") == 0 and bool(supplier.get("data", {}).get("records"))
    check(
        "supplier_page returns real data",
        supplier_ok,
        f"records={len(supplier.get('data', {}).get('records', []))}",
    )

    part = parse_tool_result(await by_name["part_page"].ainvoke({"current": 1, "size": 3}))
    part_ok = part.get("code") == 0 and bool(part.get("data", {}).get("records"))
    check("part_page returns real data", part_ok, f"records={len(part.get('data', {}).get('records', []))}")

    warning = parse_tool_result(await by_name["inventory_warning"].ainvoke({}))
    check("inventory_warning ok", warning.get("code") == 0, f"items={len(warning.get('data') or [])}")

    try:
        from src.core.settings import get_llm  # noqa: E402

        reply = get_llm(thinking=False).invoke("只回复：OK")
        content = getattr(reply, "content", str(reply))
        check("llm call", bool(content.strip()), content.strip()[:20])
    except Exception as exc:  # noqa: BLE001
        check("llm call", False, f"{type(exc).__name__}: {str(exc)[:80]}")

    failed = [name for name, ok, _ in RESULTS if not ok]
    print()
    print(f"PHASE S0: {'PASS' if not failed else 'FAIL'} ({len(RESULTS) - len(failed)}/{len(RESULTS)})")
    if failed:
        print("failed:", ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
