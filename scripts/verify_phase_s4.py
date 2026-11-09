"""S4 阶段门禁：RAG 入库、检索、引用与拒答。

覆盖：增量同步、Qdrant 点数、kb_search 相关/无关问题、kb_get_document、kb_cite。

用法：conda run -n procurement python scripts/verify_phase_s4.py
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
    from src.kb.sync import sync

    summary = sync("1")
    check("kb sync", summary["totalPoints"] >= 20,
          f"added={summary['documentsAdded']} points={summary['totalPoints']}")

    admin_id = login("admin", "Admin@123")
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient(
        {
            "erp": {
                "url": f"{MCP_URL}/sse",
                "transport": "sse",
                "headers": {
                    "X-Internal-Token": TOKEN,
                    "X-User-Id": admin_id,
                    "X-Request-Id": "s4-gate",
                },
            }
        }
    )
    tools = await client.get_tools()
    names = {tool.name for tool in tools}
    by_name = {tool.name: tool for tool in tools}
    check("kb tools present", {"kb_search", "kb_get_document", "kb_cite"}.issubset(names),
          f"count={len(tools)}")

    async def call(tool: str, args: dict) -> dict:
        return parse_result(await by_name[tool].ainvoke(args))

    policy = await call("kb_search", {"query": "采购金额达到多少需要财务审批", "top_k": 5})
    policy_hits = (policy.get("data") or {}).get("results") or []
    check("kb_search policy question", bool(policy_hits),
          f"hits={len(policy_hits)} top={(policy_hits[0]['citation'] if policy_hits else None)}")
    check("policy citation", any("内部采购管理制度" in row["citation"] for row in policy_hits),
          f"citations={[row['citation'] for row in policy_hits][:3]}")

    supplier = await call("kb_search", {"query": "供应商准入需要哪些资质", "top_k": 5})
    supplier_hits = (supplier.get("data") or {}).get("results") or []
    check("kb_search supplier question", bool(supplier_hits)
          and any("供应商准入" in row["citation"] for row in supplier_hits),
          f"hits={len(supplier_hits)}")

    irrelevant = await call("kb_search", {"query": "今天北京天气怎么样", "top_k": 5})
    irrelevant_hits = (irrelevant.get("data") or {}).get("results") or []
    check("kb_search refuses unrelated", len(irrelevant_hits) == 0, f"hits={len(irrelevant_hits)}")

    document = await call("kb_get_document", {"id": 1})
    check("kb_get_document", bool((document.get("data") or {}).get("downloadUrl")))

    cite = await call("kb_cite", {"doc_id": 1, "page": 2})
    citation = (cite.get("data") or {}).get("citation")
    check("kb_cite", bool(citation) and "第2页" in citation, f"citation={citation}")

    failed = [name for name, ok, _ in RESULTS if not ok]
    print()
    print(f"PHASE S4: {'PASS' if not failed else 'FAIL'} ({len(RESULTS) - len(failed)}/{len(RESULTS)})")
    if failed:
        print("failed:", ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
