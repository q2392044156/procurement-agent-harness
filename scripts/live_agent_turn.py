"""真实 Agent 单轮对话：LLM + MCP + 工具追踪。

用法：conda run -n procurement python scripts/live_agent_turn.py
"""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=True)

from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

from src.agent.main_agent import create_main_agent  # noqa: E402
from src.core.contracts import ProcurementContext  # noqa: E402

QUERY = "请列出当前库存预警的物资，并给出补货建议"


async def main() -> int:
    context = ProcurementContext(user_id="1", username="系统管理员", preferences={})
    agent = create_main_agent(user_context=context, checkpointer=InMemorySaver(), store=None)
    result = await asyncio.wait_for(
        agent.ainvoke(
            {"messages": [{"role": "user", "content": QUERY}]},
            config={"configurable": {"thread_id": "s6-live-turn"}},
        ),
        timeout=300,
    )
    messages = result.get("messages", [])
    last = messages[-1] if messages else None
    content = getattr(last, "content", str(last)) if last else ""
    print("QUERY:", QUERY)
    print("REPLY:", str(content)[:1200])
    print("REPLY_CHARS:", len(str(content)))
    print("MESSAGES:", len(messages))
    return 0 if str(content).strip() else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
