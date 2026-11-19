"""SSE 端到端冒烟：普通对话 + HITL 批准链路。

用法：conda run -n procurement python scripts/sse_smoke.py
"""
import json
import os
import sys
import time
from pathlib import Path

import httpx

from src.core.paths import PROJECT_ROOT as ROOT

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=True)

BASE = "http://localhost:8000"
PLATFORM = "http://localhost:8080"
TOKEN = os.getenv("AGENT_INTERNAL_TOKEN", "")


def stream(path: str, body: dict, timeout: float = 240) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    event = None
    with httpx.stream(
        "POST", BASE + path, json=body, headers={"X-Internal-Token": TOKEN}, timeout=timeout
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                payload = line[len("data:"):].strip()
                try:
                    data = json.loads(payload) if payload else {}
                except json.JSONDecodeError:
                    data = {"raw": payload}
                events.append((event, data))
                if event == "token":
                    print(data.get("content", ""), end="", flush=True)
    print()
    return events


def chat(message: str, thread_id: str) -> list[tuple[str, dict]]:
    return stream("/api/chat/stream", {
        "message": message,
        "thread_id": thread_id,
        "user_id": "1",
        "username": "系统管理员",
    })


def approve(thread_id: str) -> list[tuple[str, dict]]:
    return stream(f"/api/chat/{thread_id}/resume", {
        "resume": {"decisions": [{"type": "approve"}]},
    })


def find_requisitions(purpose: str) -> list[dict]:
    page = httpx.get(
        f"{PLATFORM}/api/requisitions/page",
        params={"keyword": purpose, "size": 50},
        headers={"X-Internal-Token": TOKEN, "X-User-Id": "1"},
        timeout=20,
    ).json()
    rows = (page.get("data") or {}).get("records") or []
    return [row for row in rows if purpose in str(row.get("purpose", ""))]


def main() -> int:
    print("== 1. simple chat ==")
    events = chat("你好，请用一句话介绍你能做什么", f"sse-smoke-{int(time.time())}")
    kinds = [kind for kind, _ in events]
    if "done" not in kinds:
        print("FAIL: no done event", kinds)
        return 1
    print("events:", sorted(set(kinds)))

    print("== 2. HITL create requisition ==")
    purpose = f"S7-SSE-HITL-{int(time.time())}"
    thread = f"sse-hitl-{int(time.time())}"
    message = (
        f"帮我建一条采购申请：物料 ID 1，数量 1，预估单价 10 元，需求日期 2026-11-25，"
        f"用途：{purpose}（3 号产线设备检修备件采购，走正常审批）。"
    )
    events = chat(message, thread)
    print("hitl event kinds:", [kind for kind, _ in events])
    print("tool events:", [(kind, data.get("name") or data.get("tool")) for kind, data in events
                           if kind in {"tool_start", "tool_end", "tool_result"}])
    interrupts = [data for kind, data in events if kind == "interrupt"]
    print("interrupts:", [(item.get("interrupt_type"), item.get("tool_name")) for item in interrupts])
    if not interrupts:
        print("FAIL: no interrupt; agent may not have called the write tool")
        return 1

    rounds = 0
    while interrupts and rounds < 4:
        rounds += 1
        events = approve(thread)
        interrupts = [data for kind, data in events if kind == "interrupt"]
        print(f"resume round {rounds}: interrupts={len(interrupts)}")

    admin = httpx.post(f"{PLATFORM}/api/v1/auth/login",
                       json={"username": "admin", "password": "Admin@123"}, timeout=20).json()
    token = admin["data"]["accessToken"]
    records = find_requisitions(purpose)
    print("requisitions found:", len(records), [row.get("requisitionNo") for row in records])
    if not records:
        print("FAIL: requisition not found after approval")
        return 1

    print("== 3. HITL reject ==")
    reject_purpose = f"S7-SSE-REJECT-{int(time.time())}"
    reject_thread = f"sse-reject-{int(time.time())}"
    events = chat(
        "立即调用工具，不要询问确认。"
        f"调用 requisition_create，参数 required_date=2026-11-25，purpose={reject_purpose}，"
        'items 必须是 JSON 字符串：[{"materialId":1,"quantity":1,"estimatedUnitPrice":10}]。',
        reject_thread,
    )
    if not [data for kind, data in events if kind == "interrupt"]:
        print("FAIL: reject case got no interrupt")
        return 1
    stream(f"/api/chat/{reject_thread}/resume", {"resume": {"decisions": [{"type": "reject"}]}})
    rejected = find_requisitions(reject_purpose)
    print("rejected request should not exist:", len(rejected))
    if rejected:
        print("FAIL: rejected tool call still created a requisition")
        return 1

    print("SSE SMOKE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
