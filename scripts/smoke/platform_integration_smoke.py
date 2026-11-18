"""平台 ↔ Harness 联调冒烟：走浏览器同款链路（JWT → 平台 → Harness → MCP → 平台 API）。

覆盖：
1. `/api/v1/ai/status` 探活；
2. 只读业务问答（应出现 supplier_* / inventory_* 工具事件与自然语言答复）；
3. 知识库问答（应带引用，或明确拒答）；
4. 写操作 HITL：requisition_create → interrupt → approve → 平台侧能查到单据；
5. 写操作 HITL：reject → 平台侧不得产生单据；
6. 会话历史：`/api/v1/ai/history` 与 `/api/v1/ai/history/{threadId}`；
7. Harness 观测接口 `/api/observability/summary`。

前置：平台与 harness 都在跑（`demo-up.ps1 -Agent`）。
用法：python -m scripts.smoke.platform_integration_smoke
"""
import json
import os
import time

import httpx
from dotenv import load_dotenv

from src.core.paths import PROJECT_ROOT as ROOT

load_dotenv(ROOT / ".env", override=False)

PLATFORM = os.getenv("PLATFORM_BASE_URL", "http://localhost:8080")
HARNESS = os.getenv("HARNESS_BASE_URL", "http://localhost:8000")
INTERNAL_TOKEN = os.getenv("AGENT_INTERNAL_TOKEN", "")

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    return ok


def login() -> tuple[str, str]:
    data = httpx.post(
        f"{PLATFORM}/api/v1/auth/login",
        json={"username": "admin", "password": "Admin@123"},
        timeout=20,
    ).json()["data"]
    return data["accessToken"], str(data["user"]["id"])


def stream(thread_id: str, message: str | None = None, resume: dict | None = None,
           token: str = "", timeout: float = 300) -> list[tuple[str, dict]]:
    """走平台代理调用 /chat/stream 或 /chat/{id}/resume，返回 (event, data) 列表。"""
    path = f"/api/v1/ai/chat/{thread_id}/resume" if resume else "/api/v1/ai/chat/stream"
    body = {"resume": resume} if resume else {"message": message, "thread_id": thread_id}
    events: list[tuple[str, dict]] = []
    event = None
    with httpx.stream("POST", PLATFORM + path, json=body,
                      headers={"Authorization": f"Bearer {token}"}, timeout=timeout) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                payload = line[len("data:"):].strip()
                try:
                    events.append((event, json.loads(payload) if payload else {}))
                except json.JSONDecodeError:
                    events.append((event, {"raw": payload}))
    return events


def answer_of(events) -> str:
    return "".join(d.get("content", "") for kind, d in events if kind == "token").strip()


def tool_names(events) -> list[str]:
    return [d.get("name") for kind, d in events if kind == "tool_start" and d.get("name")]


def interrupts_of(events) -> list[dict]:
    return [d for kind, d in events if kind == "interrupt"]


def find_requisitions(keyword: str, user_id: str) -> list[dict]:
    page = httpx.get(
        f"{PLATFORM}/api/requisitions/page",
        params={"keyword": keyword, "size": 50},
        headers={"X-Internal-Token": INTERNAL_TOKEN, "X-User-Id": user_id},
        timeout=20,
    ).json()
    rows = (page.get("data") or {}).get("records") or []
    return [row for row in rows if keyword in str(row.get("purpose", ""))]


def main() -> int:
    stamp = int(time.time())
    token, user_id = login()

    # 1. 探活
    status = httpx.get(f"{PLATFORM}/api/v1/ai/status",
                       headers={"Authorization": f"Bearer {token}"}, timeout=20).json()
    check("ai/status 探活", status.get("code") == 0 and status["data"]["enabled"] is True,
          str(status.get("data")))

    # 2. 只读业务问答
    thread = f"it-readonly-{stamp}"
    events = stream(thread, "查询前 3 个供应商，列出名称和状态", token=token)
    names = tool_names(events)
    text = answer_of(events)
    check("只读问答：走 MCP 工具", any(n and n.startswith("supplier") for n in names), f"tools={names}")
    check("只读问答：有答复且以 done 收尾",
          bool(text) and any(kind == "done" for kind, _ in events), f"{len(text)} chars")

    # 3. 知识库问答（带引用，或明确拒答）
    kb_thread = f"it-kb-{stamp}"
    kb_events = stream(kb_thread, "根据知识库说明供应商准入需要哪些资质材料", token=token)
    kb_text = answer_of(kb_events)
    cited = "《" in kb_text or "【" in kb_text
    refused = "没有找到依据" in kb_text or "没有找到" in kb_text and "依据" in kb_text
    check("知识库问答：命中引用或明确拒答", cited or refused,
          f"cited={cited} text={kb_text[:80]!r}")
    check("知识库问答：kb_search 被调用",
          "kb_search" in (tool_names(kb_events) or []), f"tools={tool_names(kb_events)}")

    # 4. HITL approve
    purpose = f"IT-APPROVE-{stamp}"
    approve_thread = f"it-hitl-{stamp}"
    msg = (
        f"帮我建一条采购申请：物料 ID 1，数量 1，预估单价 10 元，需求日期 2026-11-25，"
        f"用途：{purpose}（3 号产线设备检修备件采购，走正常审批）。"
    )
    events = stream(approve_thread, msg, token=token)
    pending = interrupts_of(events)
    check("HITL：写操作触发中断",
          bool(pending) and pending[0].get("interrupt_type") == "hitl_approval",
          str([(p.get("interrupt_type"), p.get("tool_name")) for p in pending]))

    rounds = 0
    while pending and rounds < 4:
        rounds += 1
        events = stream(approve_thread, resume={"decisions": [{"type": "approve"}]}, token=token)
        pending = interrupts_of(events)
    check("HITL：批准后流结束", rounds > 0 and not pending, f"resume rounds={rounds}")

    rows = find_requisitions(purpose, user_id)
    check("HITL：批准后平台侧存在单据", bool(rows),
          str([row.get("requisitionNo") for row in rows]))

    # 5. HITL reject
    reject_purpose = f"IT-REJECT-{stamp}"
    reject_thread = f"it-reject-{stamp}"
    reject_msg = (
        f"帮我建一条采购申请：物料 ID 1，数量 1，预估单价 10 元，需求日期 2026-11-25，"
        f"用途：{reject_purpose}（3 号产线设备检修备件采购，走正常审批）。"
    )
    events = stream(reject_thread, reject_msg, token=token)
    check("HITL：拒绝用例也先中断", bool(interrupts_of(events)))
    stream(reject_thread, resume={"decisions": [{"type": "reject"}]}, token=token)
    rejected_rows = find_requisitions(reject_purpose, user_id)
    check("HITL：拒绝后平台侧不产生单据", not rejected_rows,
          f"found={len(rejected_rows)}")

    # 6. 图表链路（沙箱 matplotlib + 中文字体 + 回传宿主机）
    chart_thread = f"it-chart-{stamp}"
    chart_events = stream(chart_thread, "把前 5 个供应商按订单金额做个柱状图", token=token,
                          timeout=300)
    chart_tools = tool_names(chart_events)
    chart_results = " ".join(
        str(d.get("content") or "") for kind, d in chart_events if kind == "tool_result"
    )
    check("图表：generate_chart 出图成功",
          "generate_chart" in chart_tools and "图表已生成" in chart_results,
          f"tools={chart_tools}")
    check("图表：文件回传宿主机并可下载",
          "文件已从沙箱下载" in chart_results,
          chart_results[-160:] if chart_results else "(no tool_result)")

    # 7. 会话历史（平台代理 → harness /api/history）
    hist = httpx.get(f"{PLATFORM}/api/v1/ai/history",
                     headers={"Authorization": f"Bearer {token}"}, timeout=30).json()
    conversations = (hist.get("data") or {}).get("conversations") or []
    thread_ids = [c.get("thread_id") for c in conversations]
    check("历史索引包含本轮会话", approve_thread in thread_ids,
          f"conversations={len(conversations)}")

    msgs = httpx.get(f"{PLATFORM}/api/v1/ai/history/{approve_thread}",
                     headers={"Authorization": f"Bearer {token}"}, timeout=30).json()
    payload = msgs.get("data") or {}
    message_rows = payload.get("messages") if isinstance(payload, dict) else payload
    check("会话消息可读取", isinstance(message_rows, list) and len(message_rows) > 0,
          f"messages={len(message_rows or [])}")

    # 8. Harness 观测接口
    summary = httpx.get(f"{HARNESS}/api/observability/summary",
                        headers={"X-Internal-Token": INTERNAL_TOKEN}, timeout=30)
    ok = summary.status_code == 200 and isinstance(summary.json(), dict)
    check("harness 观测接口可用", ok, f"status={summary.status_code}")

    failed = [name for name, ok, _ in RESULTS if not ok]
    print()
    print(f"PLATFORM INTEGRATION: {'PASS' if not failed else 'FAIL'} "
          f"({len(RESULTS) - len(failed)}/{len(RESULTS)})")
    if failed:
        print("失败项:", failed)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
