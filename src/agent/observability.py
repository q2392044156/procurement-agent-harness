"""轻量级 Turn 级可观测性：OTel 风格 trace_id + 工具/模型/轮次汇总。

不依赖外部 APM；统一写入 logs/turn_trace.jsonl，供 API 与 HTML 报告消费。
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TURN_FILE = Path(os.getenv("TURN_TRACE_FILE", str(ROOT / "logs" / "turn_trace.jsonl")))
_LOCK = threading.Lock()


@dataclass
class TraceContext:
    """一次用户请求（一个 SSE turn）的聚合上下文。"""

    trace_id: str
    thread_id: str | None
    user_id: str | None
    started: float
    started_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    tools: list[dict[str, Any]] = field(default_factory=list)
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    errors: int = 0
    interrupts: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add_tool(self, name: str, status: str, duration_ms: float, error: str | None = None) -> None:
        with self._lock:
            self.tools.append({
                "name": name,
                "status": status,
                "duration_ms": round(duration_ms, 1),
                "error": error,
            })
            if status == "error":
                self.errors += 1

    def add_model(self, model: str, input_tokens: int, output_tokens: int,
                  duration_ms: float, estimated: bool) -> None:
        with self._lock:
            self.model_calls += 1
            self.input_tokens += int(input_tokens or 0)
            self.output_tokens += int(output_tokens or 0)

    def mark_interrupt(self) -> None:
        with self._lock:
            self.interrupts += 1

    def snapshot(self, status: str) -> dict[str, Any]:
        with self._lock:
            tools = list(self.tools)
            return {
                "schema": "procuremind.turn.v1",
                "trace_id": self.trace_id,
                "thread_id": self.thread_id,
                "user_id": self.user_id,
                "started_at": self.started_at,
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "duration_ms": round((time.perf_counter() - self.started) * 1000, 1),
                "status": status,
                "interrupts": self.interrupts,
                "model_calls": self.model_calls,
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "tool_calls": len(tools),
                "tool_errors": self.errors,
                "tools": tools,
            }


_current: ContextVar[TraceContext | None] = ContextVar("procuremind_trace", default=None)


def new_trace_id() -> str:
    """32 位十六进制，兼容 OpenTelemetry trace_id 形态。"""
    return uuid.uuid4().hex


def start_trace(thread_id: str | None, user_id: str | None) -> tuple[TraceContext, Any]:
    context = TraceContext(
        trace_id=new_trace_id(),
        thread_id=thread_id,
        user_id=user_id,
        started=time.perf_counter(),
    )
    return context, _current.set(context)


def current_trace() -> TraceContext | None:
    return _current.get()


def reset_trace(token: Any) -> None:
    try:
        _current.reset(token)
    except (ValueError, LookupError):
        pass


def finish_trace(context: TraceContext, status: str = "ok") -> dict[str, Any]:
    record = context.snapshot(status)
    TURN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        try:
            if TURN_FILE.exists() and TURN_FILE.stat().st_size > 10 * 1024 * 1024:
                os.replace(TURN_FILE, TURN_FILE.with_suffix(TURN_FILE.suffix + ".1"))
        except OSError:
            pass
        try:
            with TURN_FILE.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass
    return record


def read_turns(limit: int = 50) -> list[dict[str, Any]]:
    if not TURN_FILE.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in TURN_FILE.read_text(encoding="utf-8").splitlines()[-max(1, limit):]:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records
