"""可观测性 API：turn 汇总、线程时间线、最近错误。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, Query

from src.agent.metrics import summarize
from src.agent.observability import TURN_FILE, read_turns

router = APIRouter(prefix="/api/observability", tags=["observability"])

ROOT = Path(__file__).resolve().parents[3]
TOOL_FILE = Path(os.getenv("TOOL_TRACE_FILE", str(ROOT / "logs" / "tool_trace.jsonl")))
MODEL_FILE = Path(os.getenv("MODEL_USAGE_FILE", str(ROOT / "logs" / "model_usage.jsonl")))


def _read_jsonl(path: Path, limit: int = 1000) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


@router.get("/summary")
def observability_summary():
    """汇总工具调用、模型用量、turn 延迟与中断。"""
    return {"code": 0, "data": summarize()}


@router.get("/turns")
def observability_turns(limit: int = Query(default=50, ge=1, le=500)):
    """最近的 turn 级 trace。"""
    return {"code": 0, "data": read_turns(limit)}


@router.get("/threads/{thread_id}")
def observability_thread(thread_id: str):
    """按 thread_id 返回工具、模型与 turn 的联合时间线。"""
    tools = [r for r in _read_jsonl(TOOL_FILE) if str(r.get("thread_id")) == thread_id]
    models = [r for r in _read_jsonl(MODEL_FILE) if str(r.get("thread_id")) == thread_id]
    turns = [r for r in _read_jsonl(TURN_FILE) if str(r.get("thread_id")) == thread_id]
    return {
        "code": 0,
        "data": {
            "thread_id": thread_id,
            "turns": turns,
            "tools": tools[-200:],
            "models": models[-200:],
        },
    }


@router.get("/errors")
def observability_errors(limit: int = Query(default=20, ge=1, le=200)):
    """最近的工具错误，便于快速定位。"""
    rows = [r for r in _read_jsonl(TOOL_FILE) if r.get("status") == "error"]
    return {"code": 0, "data": rows[-limit:]}
