"""平台前端 SSE 代理冒烟：JWT → 平台 → Harness，验证浏览器侧可用的链路。

用法：conda run -n procurement python scripts/platform_proxy_smoke.py
"""
import json
import time

import httpx

PLATFORM = "http://localhost:8080"


def main() -> int:
    login = httpx.post(
        f"{PLATFORM}/api/v1/auth/login",
        json={"username": "admin", "password": "Admin@123"},
        timeout=20,
    ).json()
    token = login["data"]["accessToken"]

    events: list[str] = []
    text: list[str] = []
    with httpx.stream(
        "POST",
        f"{PLATFORM}/api/v1/ai/chat/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "用一句话介绍你能做什么", "thread_id": f"proxy-smoke-{int(time.time())}"},
        timeout=180,
    ) as response:
        response.raise_for_status()
        event = None
        for line in response.iter_lines():
            if line.startswith("event:"):
                event = line[len("event:"):].strip()
                events.append(event)
            elif line.startswith("data:") and event == "token":
                payload = line[len("data:"):].strip()
                try:
                    text.append(json.loads(payload).get("content", ""))
                except json.JSONDecodeError:
                    pass

    answer = "".join(text).strip()
    print("events:", sorted(set(events)))
    print("answer chars:", len(answer))
    print("answer:", answer[:200])
    if "done" not in events or not answer:
        print("PLATFORM PROXY: FAIL")
        return 1
    print("PLATFORM PROXY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
