"""真机工具评测：不经过 LLM，直接通过 MCP 调用真实平台，验证数据口径与权限。

用法：conda run -n procurement python scripts/eval_live.py
输出：evals/live/summary.json
"""
import asyncio
import json
import os
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=True)

PLATFORM = os.getenv("ERP_BASE_URL", "http://localhost:8080")
MCP_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8001")
TOKEN = os.getenv("AGENT_INTERNAL_TOKEN", "")


def login(username: str, password: str) -> str:
    response = httpx.post(
        f"{PLATFORM}/api/v1/auth/login",
        json={"username": username, "password": password},
        timeout=20,
    )
    response.raise_for_status()
    return str(response.json()["data"]["user"]["id"])


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
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        return {}


async def main() -> int:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    admin_id = login("admin", "Admin@123")
    client = MultiServerMCPClient(
        {
            "erp": {
                "url": f"{MCP_URL}/sse",
                "transport": "sse",
                "headers": {
                    "X-Internal-Token": TOKEN,
                    "X-User-Id": admin_id,
                    "X-Request-Id": "live-eval",
                },
            }
        }
    )
    tools = {tool.name: tool for tool in await client.get_tools()}

    async def call(name: str, args: dict) -> tuple[dict, float]:
        started = time.perf_counter()
        result = parse(await tools[name].ainvoke(args))
        return result, round((time.perf_counter() - started) * 1000, 1)

    cases = []

    def page(data: dict) -> dict:
        return data.get("data") or {}

    async def check(name: str, ok: bool, detail: str, latency: float) -> None:
        cases.append({"name": name, "ok": ok, "detail": detail, "latencyMs": latency})
        print(f"{'PASS' if ok else 'FAIL'}  {name}  [{detail}; {latency}ms]")

    data, ms = await call("supplier_page", {"current": 1, "size": 3})
    records = page(data).get("records") or []
    await check("supplier_page", data.get("code") == 0 and len(records) > 0,
                f"records={len(records)}", ms)

    data, ms = await call("part_page", {"current": 1, "size": 3})
    records = page(data).get("records") or []
    await check("part_page", data.get("code") == 0 and len(records) > 0,
                f"records={len(records)}", ms)

    data, ms = await call("requisition_page", {"current": 1, "size": 5})
    await check("requisition_page", data.get("code") == 0 and page(data).get("total", 0) >= 1,
                f"total={page(data).get('total')}", ms)

    data, ms = await call("budget_list", {})
    await check("budget_list", data.get("code") == 0 and len(data.get("data") or []) == 4,
                f"departments={len(data.get('data') or [])}", ms)

    data, ms = await call("contract_page", {"current": 1, "size": 5})
    await check("contract_page", data.get("code") == 0 and page(data).get("total", 0) >= 2,
                f"total={page(data).get('total')}", ms)

    data, ms = await call("inventory_risk", {})
    rows = data.get("data") or []
    if not isinstance(rows, list):
        rows = []
    mouse = next((row for row in rows if isinstance(row, dict) and row.get("materialCode") == "MOUSE-USB-001"), None)
    risk_ok = data.get("code") == 0 and (
        not rows or all(isinstance(row, dict) and "netGap" in row for row in rows)
    )
    await check("inventory_risk", risk_ok, f"rows={len(rows)}", ms)

    suppliers, ms = await call("supplier_page", {"current": 1, "size": 5})
    supplier_rows = page(suppliers).get("records") or []
    supplier_id = supplier_rows[0]["id"] if supplier_rows else 1
    data, ms = await call("supplier_scorecard", {"supplier_id": int(supplier_id), "year": 0})
    score = data.get("data") or {}
    await check("supplier_scorecard", data.get("code") == 0 and "amount" in score,
                f"supplier={supplier_id} amount={score.get('amount')}", ms)

    data, ms = await call("spend_analysis", {"year": 0, "group_by": "department"})
    total = float((data.get("data") or {}).get("total") or 0)
    await check("spend_analysis", data.get("code") == 0 and total > 0,
                f"total={total}", ms)

    data, ms = await call("kb_search", {"query": "供应商准入需要哪些资质", "top_k": 3})
    hits = (data.get("data") or {}).get("results") or []
    await check("kb_search", data.get("code") == 0 and len(hits) > 0,
                f"hits={len(hits)}", ms)

    data, ms = await call("inventory_warning", {})
    await check("inventory_warning", data.get("code") == 0, f"items={len(data.get('data') or [])}", ms)

    # ===== 扩展场景（P1：10 -> 30）=====
    orders, ms = await call("order_page", {"current": 1, "size": 5})
    order_rows = page(orders).get("records") or []
    order_id = int(order_rows[0]["id"]) if order_rows else 1
    await check("order_page", orders.get("code") == 0 and bool(order_rows),
                f"rows={len(order_rows)}", ms)

    parts, ms = await call("part_page", {"current": 1, "size": 5})
    part_rows = page(parts).get("records") or []
    part_id = int(part_rows[0]["id"]) if part_rows else 1
    warehouses, ms = await call("warehouse_list", {})
    warehouse_rows = warehouses.get("data") or []
    warehouse_id = int(warehouse_rows[0]["id"]) if warehouse_rows else 1
    contracts, ms = await call("contract_page", {"current": 1, "size": 5})
    contract_rows = page(contracts).get("records") or []
    contract_id = int(contract_rows[0]["id"]) if contract_rows else 1

    extra_calls = [
        ("supplier_query", {"name": "科技"}),
        ("part_search", {"name": "鼠标"}),
        ("part_query", {"id": part_id}),
        ("part_by_supplier", {"supplier_id": supplier_id}),
        ("order_get", {"id": order_id}),
        ("order_statistics", {}),
        ("workflow_done", {}),
        ("workflow_timeline", {"business_type": "PURCHASE_ORDER", "business_id": order_id}),
        ("dashboard_summary", {}),
        ("alerts_summary", {}),
        ("warehouse_get", {"id": warehouse_id}),
        ("issue_page", {"current": 1, "size": 5}),
        ("budget_list", {}),
        ("contract_get", {"id": contract_id}),
        ("part_price_history", {"id": part_id}),
        ("price_trend", {"material_id": part_id}),
        ("approval_sla", {}),
        ("inventory_check", {}),
        ("kb_get_document", {"id": 1}),
        ("kb_cite", {"doc_id": 1, "page": 1}),
    ]
    for name, args in extra_calls:
        data, ms = await call(name, args)
        await check(name, data.get("code") == 0, f"args={args}", ms)

    summary = {
        "platform": PLATFORM,
        "cases": len(cases),
        "passed": sum(1 for case in cases if case["ok"]),
        "avgLatencyMs": round(sum(case["latencyMs"] for case in cases) / len(cases), 1),
        "maxLatencyMs": max(case["latencyMs"] for case in cases),
        "results": cases,
    }
    output = ROOT / "evals" / "live" / "summary.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nLIVE EVAL: {summary['passed']}/{summary['cases']} passed, "
          f"avg={summary['avgLatencyMs']}ms max={summary['maxLatencyMs']}ms")
    return 0 if summary["passed"] == summary["cases"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
