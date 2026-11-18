"""S3 阶段门禁：写入工具面 + 幂等 + 审批闭环。

流程：申请人建申请 → 重放（应返回同一单）→ 提交 → 部门经理/采购员审批 →
采购员转订单 → 重放（应返回同一订单）→ 取消订单。另校验 HITL 配置与越权 403。

用法：conda run -n procurement python scripts/verify_phase_s3.py
"""
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from src.core.paths import PROJECT_ROOT as ROOT

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=True)

import httpx  # noqa: E402

PLATFORM = os.getenv("ERP_BASE_URL", "http://localhost:8080")
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


def internal(uid: str) -> dict:
    return {"X-Internal-Token": TOKEN, "X-User-Id": uid, "Content-Type": "application/json"}


def get_json(path: str, uid: str) -> dict:
    return httpx.get(f"{PLATFORM}{path}", headers=internal(uid), timeout=20).json()


def post_json(path: str, uid: str, body=None) -> tuple[int, dict]:
    response = httpx.post(f"{PLATFORM}{path}", json=body, headers=internal(uid), timeout=20)
    try:
        return response.status_code, response.json()
    except Exception:  # noqa: BLE001
        return response.status_code, {}


def main() -> int:
    requester_id, _ = login("requester", "Request@123")
    purchaser_id, purchaser_token = login("purchaser", "Purchase@123")
    manager_id, manager_token = login("manager", "Manager@123")

    purpose = f"S3 门禁-{int(time.time())}"
    body = {
        "requiredDate": (date.today() + timedelta(days=7)).isoformat(),
        "purpose": purpose,
        "items": [{"materialId": 1, "quantity": 1, "estimatedUnitPrice": 10}],
    }
    status, created = post_json("/api/requisitions", requester_id, body)
    req_id = (created.get("data") or {}).get("id")
    check("requisition create", status == 200 and created.get("code") == 0 and req_id,
          f"id={req_id} status={status}")

    _, replay = post_json("/api/requisitions", requester_id, body)
    replay_id = (replay.get("data") or {}).get("id")
    check("create is idempotent", str(replay_id) == str(req_id), f"first={req_id} replay={replay_id}")

    status, submitted = post_json(f"/api/requisitions/{req_id}/submit", requester_id)
    submit_status = (submitted.get("data") or {}).get("status")
    check("requisition submit", status == 200 and submitted.get("code") == 0 and submit_status != "DRAFT",
          f"status={submit_status}")

    # 审批闭环：按角色扫待办，直到申请变为 APPROVED
    approvers = [
        ("manager", manager_id, manager_token),
        ("purchaser", purchaser_id, purchaser_token),
        ("finance", *login("finance", "Finance@123")),
        ("gm", *login("gm", "Gm@123")),
    ]
    approved = False
    for _ in range(6):
        detail = get_json(f"/api/requisitions/get/{req_id}", requester_id)
        current = (detail.get("data") or {}).get("status")
        if current == "APPROVED":
            approved = True
            break
        for role, uid, jwt in approvers:
            tasks = httpx.get(
                f"{PLATFORM}/api/v1/workflow/tasks",
                headers={"Authorization": f"Bearer {jwt}"},
                timeout=20,
            ).json().get("data") or []
            task = next((t for t in tasks if t.get("businessKey") == f"REQUISITION:{req_id}"), None)
            if task:
                response = httpx.post(
                    f"{PLATFORM}/api/v1/workflow/{task['id']}/approve",
                    json={"comment": "S3 门禁"},
                    headers={"Authorization": f"Bearer {jwt}"},
                    timeout=20,
                )
                print(f"      approved by {role}: {response.status_code}")
                break
    final_detail = get_json(f"/api/requisitions/get/{req_id}", requester_id)
    check("approval chain finished", approved or (final_detail.get("data") or {}).get("status") == "APPROVED",
          f"status={(final_detail.get('data') or {}).get('status')}")

    denied_status, _ = post_json(
        f"/api/requisitions/{req_id}/convert",
        requester_id,
        {"supplierId": 1, "deliveryDate": (date.today() + timedelta(days=7)).isoformat(), "taxRate": 0.13},
    )
    check("applicant cannot convert", denied_status == 403, f"status={denied_status}")

    suppliers = get_json("/api/suppliers/page?status=QUALIFIED&size=5", purchaser_id)
    supplier_id = ((suppliers.get("data") or {}).get("records") or [{}])[0].get("id")
    convert_body = {
        "supplierId": int(supplier_id),
        "deliveryDate": (date.today() + timedelta(days=7)).isoformat(),
        "taxRate": 0.13,
        "terms": "S3 门禁",
    }
    status, converted = post_json(f"/api/requisitions/{req_id}/convert", purchaser_id, convert_body)
    order_id = (converted.get("data") or {}).get("id")
    order_status = (converted.get("data") or {}).get("status")
    check("convert to order", status == 200 and converted.get("code") == 0 and order_id,
          f"order={order_id} status={order_status}")

    _, convert_replay = post_json(f"/api/requisitions/{req_id}/convert", purchaser_id, convert_body)
    check("convert is idempotent", str((convert_replay.get("data") or {}).get("id")) == str(order_id),
          f"order={order_id} replay={(convert_replay.get('data') or {}).get('id')}")

    cancel_body = {"reason": "S3 门禁-取消"}
    status, cancelled = post_json(f"/api/orders/{order_id}/cancel", purchaser_id, cancel_body)
    cancelled_status = (cancelled.get("data") or {}).get("status")
    check("order cancel", status == 200 and cancelled.get("code") == 0 and cancelled_status == "CANCELLED",
          f"status={cancelled_status}")

    _, cancel_replay = post_json(f"/api/orders/{order_id}/cancel", purchaser_id, cancel_body)
    check("cancel is idempotent", (cancel_replay.get("data") or {}).get("status") == "CANCELLED")

    from src.core.settings import INTERRUPT_ON_TOOLS  # noqa: E402

    expected_hitl = {"requisition_create", "requisition_submit", "requisition_convert", "order_cancel"}
    check("hitl covers write tools", expected_hitl.issubset(INTERRUPT_ON_TOOLS),
          ",".join(sorted(expected_hitl - set(INTERRUPT_ON_TOOLS))) or "ok")

    failed = [name for name, ok, _ in RESULTS if not ok]
    print()
    print(f"PHASE S3: {'PASS' if not failed else 'FAIL'} ({len(RESULTS) - len(failed)}/{len(RESULTS)})")
    if failed:
        print("failed:", ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
