"""生成层验收：知识库回答必须带引用；无关问题必须拒答。"""
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=True)
TOKEN = os.getenv("AGENT_INTERNAL_TOKEN", "")
BASE = "http://localhost:8000"
CITATION = re.compile(r"《[^》]+》第\d+页")


def ask(question: str, thread: str) -> str:
    answer = []
    with httpx.stream(
        "POST", f"{BASE}/api/chat/stream",
        headers={"X-Internal-Token": TOKEN, "X-User-Id": "1", "Content-Type": "application/json"},
        json={"message": question, "thread_id": thread, "user_id": "1"}, timeout=180,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if line.startswith("data:") and '"source"' in line:
                try:
                    answer.append(json.loads(line[5:].strip()).get("content", ""))
                except json.JSONDecodeError:
                    pass
    return "".join(answer).strip()


def main() -> int:
    policy = ask("采购制度里供应商准入需要哪些资质？请依据知识库回答。", f"rag-gen-policy-{int(time.time())}")
    print("POLICY_CHARS:", len(policy))
    print("POLICY_CITATION:", bool(CITATION.search(policy)))
    print("POLICY_HEAD:", policy[:220])
    unrelated = ask("今天北京天气怎么样？", f"rag-gen-unrelated-{int(time.time())}")
    print("UNRELATED_HEAD:", unrelated[:160])
    refusal = any(word in unrelated for word in ("没有找到依据", "无法查询", "无法回答", "不能", "未找到"))
    print("UNRELATED_REFUSAL:", refusal)
    if not CITATION.search(policy) or not refusal:
        return 1
    print("RAG GENERATION: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
