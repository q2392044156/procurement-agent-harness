"""S2 阶段门禁：分析能力。

校验 5 个分析工具（记分卡、库存风险、花费分析、审批 SLA、价格趋势）返回真实数据，
并检查数值口径字段存在。

用法：conda run -n procurement python scripts/verify_phase_s2.py
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


def login(username: str, password: str) -> tuple[str, str]:
    response = httpx.post(
        f"{PLATFORM}/api/v1/auth/login",
        json={"username": username, "password": password},
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()["data"]
    return str(data["user"]["id"]), str(data["accessToken"])


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


def client_for(user_id: str):
    from langchain_mcp_adapters.client import MultiServerMCPClient

    return MultiServerMCPClient(
        {
            "erp": {
                "url": f"{MCP_URL}/sse",
                "transport": "sse",
                "headers": {
                    "X-Internal-Token": TOKEN,
                    "X-User-Id": user_id,
                    "X-Request-Id": "s2-gate",
                },
            }
        }
    )


async def main() -> int:
    admin_id, admin_token = login("admin", "Admin@123")
    client = client_for(admin_id)
    tools = await client.get_tools()
    names = {tool.name for tool in tools}
    by_name = {tool.name: tool for tool in tools}

    check("mcp tool count", len(tools) >= 43, f"count={len(tools)}")
    expected = {"supplier_scorecard", "inventory_risk", "spend_analysis", "approval_sla", "price_trend"}
    check("analytics tools present", expected.issubset(names), ",".join(sorted(expected - names)) or "ok")

    async def call(tool: str, args: dict) -> dict:
        return parse_result(await by_name[tool].ainvoke(args))

    orders = await call("order_page", {"current": 1, "size": 5})
    records = (orders.get("data") or {}).get("records") or []
    detail = {}
    if records:
        detail = (await call("order_get", {"id": int(records[0]["id"])})).get("data") or {}
    supplier_id = int(detail.get("supplierId") or 1)
    scorecard = await call("supplier_scorecard", {"supplier_id": supplier_id, "year": 0})
    data = scorecard.get("data") or {}
    check(
        "supplier_scorecard",
        scorecard.get("code") == 0 and "amount" in data and "orderCount" in data,
        f"supplier={supplier_id} amount={data.get('amount')} orders={data.get('orderCount')}",
    )

    risk = await call("inventory_risk", {})
    if not (risk.get("data") or []):
        # 幂等补一个低库存场景：把 MOUSE 库存降到安全库存以下
        balances = httpx.get(
            f"{PLATFORM}/api/v1/inventory/balances/page",
            params={"keyword": "MOUSE-USB-001", "size": 5},
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=20,
        ).json()
        rows = (balances.get("data") or {}).get("records") or []
        if rows:
            row = rows[0]
            quantity = float(row["quantity"])
            min_stock = float(row["minStock"])
            if quantity > min_stock:
                warehouses = await call("warehouse_list", {})
                main_wh = next(w for w in (warehouses.get("data") or []) if w.get("code") == "MAIN")
                parts = await call("part_search", {"name": row["materialName"]})
                low_material_id = int(parts["data"][0]["id"])
                _, warehouse_token = login("warehouse", "Warehouse@123")
                issue_quantity = quantity - min_stock + 1
                response = httpx.post(
                    f"{PLATFORM}/api/v1/inventory/issues",
                    json={
                        "warehouseId": int(main_wh["id"]),
                        "materialId": low_material_id,
                        "quantity": issue_quantity,
                        "purpose": "S2 门禁-低库存场景",
                    },
                    headers={"Authorization": f"Bearer {warehouse_token}"},
                    timeout=20,
                )
                check("seed low stock scenario", response.status_code in (200, 201),
                      f"qty={issue_quantity} status={response.status_code}")
        risk = await call("inventory_risk", {})

    risk_rows = risk.get("data") or []
    mouse = next((row for row in risk_rows if row.get("materialCode") == "MOUSE-USB-001"), None)
    risk_ok = (
        risk.get("code") == 0
        and bool(risk_rows)
        and all("netGap" in row and "riskLevel" in row for row in risk_rows)
        and mouse is not None
        and float(mouse["netGap"]) > 0
    )
    check("inventory_risk", risk_ok,
          f"items={len(risk_rows)} mouseNetGap={mouse.get('netGap') if mouse else None}")

    spend = await call("spend_analysis", {"year": 0, "group_by": "department"})
    spend_data = spend.get("data") or {}
    spend_total = float(spend_data.get("total") or 0)
    check(
        "spend_analysis",
        spend.get("code") == 0 and spend_total > 0,
        f"total={spend_data.get('total')} groups={len(spend_data.get('records') or [])}",
    )

    sla = await call("approval_sla", {"threshold_hours": 24})
    sla_data = sla.get("data") or {}
    check(
        "approval_sla",
        sla.get("code") == 0 and isinstance(sla_data.get("total"), int),
        f"total={sla_data.get('total')} overdue={sla_data.get('overdue')}",
    )

    material_id = 5
    items = detail.get("items") or []
    if items:
        material_id = int(items[0]["materialId"])
    trend = await call("price_trend", {"material_id": material_id, "months": 12})
    trend_data = trend.get("data") or {}
    check(
        "price_trend",
        trend.get("code") == 0 and trend_data.get("sampleCount", 0) >= 1,
        f"material={material_id} samples={trend_data.get('sampleCount')}",
    )

    failed = [name for name, ok, _ in RESULTS if not ok]
    print()
    print(f"PHASE S2: {'PASS' if not failed else 'FAIL'} ({len(RESULTS) - len(failed)}/{len(RESULTS)})")
    if failed:
        print("failed:", ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
