"""读取 tool_trace.jsonl 并计算工具调用指标。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRACE = ROOT / "logs" / "tool_trace.jsonl"
USAGE_FILE = ROOT / "logs" / "model_usage.jsonl"


def _usage() -> dict:
    records = []
    if USAGE_FILE.exists():
        for line in USAGE_FILE.read_text(encoding="utf-8").splitlines():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    input_tokens = sum(int(r.get("input_tokens") or 0) for r in records)
    output_tokens = sum(int(r.get("output_tokens") or 0) for r in records)
    input_price = float(os.getenv("MODEL_INPUT_PRICE_PER_M", "0.15"))
    output_price = float(os.getenv("MODEL_OUTPUT_PRICE_PER_M", "0.60"))
    cost = input_tokens / 1_000_000 * input_price + output_tokens / 1_000_000 * output_price
    by_model: dict[str, int] = {}
    for record in records:
        model = str(record.get("model") or "unknown")
        by_model[model] = by_model.get(model, 0) + 1
    return {
        "modelCalls": len(records),
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "estimatedCostUsd": round(cost, 4),
        "byModel": by_model,
    }


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(ratio * (len(ordered) - 1)))))
    return ordered[index]


def summarize(path: Path | None = None) -> dict:
    trace = Path(path or DEFAULT_TRACE)
    records: list[dict] = []
    for candidate in (trace, trace.with_suffix(trace.suffix + ".1")):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    durations = [float(r["duration_ms"]) for r in records if r.get("duration_ms") is not None]
    errors = [r for r in records if r.get("status") == "error"]
    by_tool: dict[str, dict] = {}
    by_thread: dict[str, dict] = {}
    for record in records:
        entry = by_tool.setdefault(record.get("tool", "unknown"), {"calls": 0, "errors": 0})
        entry["calls"] += 1
        if record.get("status") == "error":
            entry["errors"] += 1
        thread = str(record.get("thread_id") or "-")
        thread_entry = by_thread.setdefault(thread, {"calls": 0, "errors": 0})
        thread_entry["calls"] += 1
        if record.get("status") == "error":
            thread_entry["errors"] += 1

    return {
        "traceFile": str(trace),
        "exists": trace.exists(),
        "calls": len(records),
        "errors": len(errors),
        "successRate": round((len(records) - len(errors)) / len(records), 3) if records else 0.0,
        "p50Ms": round(_percentile(durations, 0.50), 1),
        "p95Ms": round(_percentile(durations, 0.95), 1),
        "maxMs": round(max(durations), 1) if durations else 0.0,
        "byTool": dict(sorted(by_tool.items())),
        "byThread": dict(sorted(by_thread.items())),
        "lastError": errors[-1].get("error") if errors else None,
        **_usage(),
    }


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    print(json.dumps(summarize(Path(target) if target else None), ensure_ascii=False, indent=2))
