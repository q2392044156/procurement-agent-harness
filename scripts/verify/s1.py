"""S1 阶段门禁：只读工具面补齐。

覆盖：申请/待办/时间线/看板/提醒/收货/仓库/出库/预算/合同/历史成交价，
并验证越权访问 `/api/budgets` 返回 403、旧入库工具已移除。

用法：conda run -n procurement python scripts/verify_phase_s1.py
"""
import asyncio
import json
import os
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


def login(username: str, password: str) -> str:
    response = httpx.post(
        f"{PLATFORM}/api/v1/auth/login",
        json={"username": username, "password": password},
        timeout=20,
    )
    response.raise_for_status()
    return str(response.json()["data"]["user"]["id"])


def parse_result(raw) -> dict:
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
    admin_id = login("admin", "Admin@123")
    applicant_id = login("requester", "Request@123")

    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient(
        {
            "erp": {
                "url": f"{MCP_URL}/sse",
                "transport": "sse",
                "headers": {
                    "X-Internal-Token": TOKEN,
                    "X-User-Id": admin_id,
                    "X-Request-Id": "s1-gate",
                },
            }
        }
    )
    tools = await client.get_tools()
    names = {tool.name for tool in tools}
    by_name = {tool.name: tool for tool in tools}

    check("mcp tool count", len(tools) >= 33, f"count={len(tools)}")
    expected = {
        "requisition_page",
        "requisition_get",
        "workflow_todo",
        "workflow_timeline",
        "dashboard_summary",
        "alerts_summary",
        "receipt_page",
        "receipt_get",
        "warehouse_list",
        "issue_page",
        "budget_list",
        "contract_page",
        "part_price_history",
    }
    check("new tools present", expected.issubset(names), ",".join(sorted(expected - names)) or "ok")
    check("stale inbound/outbound removed", not ({"inventory_inbound", "inventory_outbound"} & names))

    async def call(tool: str, args: dict) -> dict:
        return parse_result(await by_name[tool].ainvoke(args))

    requisitions = await call("requisition_page", {"current": 1, "size": 5})
    check("requisition_page", requisitions.get("code") == 0,
          f"total={requisitions.get('data', {}).get('total')}")

    todo = await call("workflow_todo", {})
    check("workflow_todo", todo.get("code") == 0 and isinstance(todo.get("data"), list),
          f"items={len(todo.get('data') or [])}")

    dashboard = await call("dashboard_summary", {})
    check("dashboard_summary", dashboard.get("code") == 0 and bool(dashboard.get("data")))

    alerts = await call("alerts_summary", {})
    check("alerts_summary", alerts.get("code") == 0 and bool(alerts.get("data")))

    receipts = await call("receipt_page", {"current": 1, "size": 5})
    check("receipt_page", receipts.get("code") == 0,
          f"total={receipts.get('data', {}).get('total')}")

    warehouses = await call("warehouse_list", {})
    check("warehouse_list", warehouses.get("code") == 0 and bool(warehouses.get("data")),
          f"items={len(warehouses.get('data') or [])}")

    issues = await call("issue_page", {"current": 1, "size": 5})
    check("issue_page", issues.get("code") == 0,
          f"total={issues.get('data', {}).get('total')}")

    budgets = await call("budget_list", {})
    check("budget_list", budgets.get("code") == 0 and bool(budgets.get("data")),
          f"items={len(budgets.get('data') or [])}")

    contracts = await call("contract_page", {"current": 1, "size": 5})
    check("contract_page", contracts.get("code") == 0,
          f"total={contracts.get('data', {}).get('total')}")

    orders = await call("order_page", {"current": 1, "size": 5})
    material_id = None
    if orders.get("code") == 0 and orders.get("data", {}).get("records"):
        order_id = orders["data"]["records"][0]["id"]
        detail = await call("order_get", {"id": int(order_id)})
        items = (detail.get("data") or {}).get("items") or []
        if items:
            material_id = int(items[0]["materialId"])
    if material_id is None:
        parts = await call("part_page", {"current": 1, "size": 1})
        material_id = int(parts["data"]["records"][0]["id"])
    history = await call("part_price_history", {"id": material_id})
    check("part_price_history", history.get("code") == 0,
          f"material={material_id} rows={len(history.get('data') or [])}")

    denied = httpx.get(
        f"{PLATFORM}/api/budgets",
        headers={"X-Internal-Token": TOKEN, "X-User-Id": applicant_id},
        timeout=10,
    )
    check("applicant denied budgets", denied.status_code == 403, f"status={denied.status_code}")

    failed = [name for name, ok, _ in RESULTS if not ok]
    print()
    print(f"PHASE S1: {'PASS' if not failed else 'FAIL'} ({len(RESULTS) - len(failed)}/{len(RESULTS)})")
    if failed:
        print("failed:", ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
