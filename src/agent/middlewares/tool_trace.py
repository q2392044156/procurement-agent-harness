"""工具调用追踪：JSONL 记录 + 延迟统计。

记录字段：request_id、thread_id、user_id、tool、args_keys、status、error、duration_ms、result_len、ts。
默认写入 ``logs/tool_trace.jsonl``，可用 ``TOOL_TRACE_FILE`` 覆盖。
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage

ROOT = Path(__file__).resolve().parents[3]
TRACE_FILE = Path(os.getenv("TOOL_TRACE_FILE", str(ROOT / "logs" / "tool_trace.jsonl")))
_LOCK = threading.Lock()


def _thread_id() -> str | None:
    try:
        from langgraph.config import get_config

        return get_config().get("configurable", {}).get("thread_id")
    except Exception:
        return None


def _append(record: dict) -> None:
    TRACE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        with TRACE_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def record_tool_call(
    tool: str,
    user_id: str | None,
    status: str,
    duration_ms: float,
    result_len: int = 0,
    error: str | None = None,
    args_keys: list[str] | None = None,
) -> None:
    """记录一次工具调用（MCP 工具包装器与中间件共用）。"""
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "request_id": str(uuid.uuid4()),
        "thread_id": _thread_id(),
        "user_id": user_id,
        "tool": tool,
        "args_keys": args_keys or [],
        "status": status,
        "error": error,
        "duration_ms": round(duration_ms, 1),
        "result_len": result_len,
    }
    try:
        _append(record)
    except Exception:
        pass


class ToolTraceMiddleware(AgentMiddleware):
    """记录每次工具调用的耗时、状态与错误类型。"""

    def __init__(self, user_id: str | None = None):
        super().__init__()
        self.user_id = user_id

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Any]],
    ) -> ToolMessage | Any:
        tool_call = getattr(request, "tool_call", {}) or {}
        name = tool_call.get("name", "unknown")
        args = tool_call.get("args", {}) or {}
        request_id = str(uuid.uuid4())
        start = time.perf_counter()
        status = "ok"
        error = None
        result_len = 0
        try:
            result = await handler(request)
            if isinstance(result, ToolMessage) and getattr(result, "status", None) == "error":
                status = "error"
                error = str(getattr(result, "content", ""))[:200]
            else:
                content = getattr(result, "content", result)
                result_len = len(content) if isinstance(content, str) else 0
            return result
        except Exception as exc:  # noqa: BLE001
            status = "error"
            error = f"{type(exc).__name__}: {exc}"[:200]
            raise
        finally:
            record = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "request_id": request_id,
                "thread_id": _thread_id(),
                "user_id": self.user_id,
                "tool": name,
                "args_keys": sorted(args.keys()) if isinstance(args, dict) else [],
                "status": status,
                "error": error,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                "result_len": result_len,
            }
            try:
                _append(record)
            except Exception:
                pass
