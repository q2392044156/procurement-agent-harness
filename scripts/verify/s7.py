"""S7 阶段门禁：部署编排与运行态检查。

检查：
1. compose 中 qdrant/mongo 容器处于运行/健康状态
2. 平台健康检查、Qdrant readyz
3. MCP 工具数量与 supplier_page 真机调用
4. KB 检索（指向 compose Qdrant）

用法：conda run -n procurement python scripts/verify_phase_s7.py
"""
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from src.core.paths import PROJECT_ROOT as ROOT

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


def container_status() -> str:
    result = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}} {{.Status}}"],
        capture_output=True, text=True, timeout=30,
    )
    return result.stdout


def parse(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    text = "".join(
        item.get("text", "") if isinstance(item, dict) else str(item)
        for item in (raw if isinstance(raw, list) else [raw])
    )
    start = text.find("{")
    if start < 0:
        return {}
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    return obj


async def main() -> int:
    status = container_status()
    check("qdrant container running", "qdrant-1" in status)
    check("mongo container running", "mongo-1" in status and "(healthy)" in status)

    try:
        health = httpx.get(f"{PLATFORM}/actuator/health", timeout=10)
        check("platform health", health.status_code == 200)
    except Exception as exc:  # noqa: BLE001
        check("platform health", False, str(exc)[:80])

    try:
        ready = httpx.get("http://localhost:6333/readyz", timeout=10)
        check("qdrant ready", ready.status_code == 200)
    except Exception as exc:  # noqa: BLE001
        check("qdrant ready", False, str(exc)[:80])

    login = httpx.post(
        f"{PLATFORM}/api/v1/auth/login",
        json={"username": "admin", "password": "Admin@123"},
        timeout=20,
    ).json()
    admin_id = str(login["data"]["user"]["id"])

    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient(
        {
            "erp": {
                "url": f"{MCP_URL}/sse",
                "transport": "sse",
                "headers": {
                    "X-Internal-Token": TOKEN,
                    "X-User-Id": admin_id,
                    "X-Request-Id": "s7-gate",
                },
            }
        }
    )
    tools = {tool.name: tool for tool in await client.get_tools()}
    check("mcp tools", len(tools) >= 51, f"count={len(tools)}")

    supplier = parse(await tools["supplier_page"].ainvoke({"current": 1, "size": 1}))
    check("mcp -> platform", supplier.get("code") == 0,
          f"records={len((supplier.get('data') or {}).get('records') or [])}")

    kb = parse(await tools["kb_search"].ainvoke({"query": "供应商准入需要哪些资质", "top_k": 3}))
    hits = (kb.get("data") or {}).get("results") or []
    check("kb over compose qdrant", kb.get("code") == 0 and len(hits) > 0,
          f"hits={len(hits)}")

    failed = [name for name, ok, _ in RESULTS if not ok]
    print()
    print(f"PHASE S7: {'PASS' if not failed else 'FAIL'} ({len(RESULTS) - len(failed)}/{len(RESULTS)})")
    if failed:
        print("failed:", ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
