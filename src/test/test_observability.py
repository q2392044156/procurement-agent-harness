"""Turn 级可观测性单元测试。"""
from __future__ import annotations

import time

from src.agent.observability import TraceContext


def test_trace_aggregates_tools_models_and_interrupt():
    context = TraceContext(
        trace_id="a" * 32,
        thread_id="thread-1",
        user_id="1",
        started=time.perf_counter(),
    )
    context.add_tool("part_search", "ok", 12.5)
    context.add_tool("kb_search", "error", 8.0, "timeout")
    context.add_model("deepseek-flash", 100, 50, 220.0, False)
    context.mark_interrupt()

    record = context.snapshot("interrupted")
    assert record["trace_id"] == "a" * 32
    assert record["thread_id"] == "thread-1"
    assert record["status"] == "interrupted"
    assert record["interrupts"] == 1
    assert record["tool_calls"] == 2
    assert record["tool_errors"] == 1
    assert record["model_calls"] == 1
    assert record["input_tokens"] == 100
    assert record["output_tokens"] == 50
    assert record["tools"][0]["name"] == "part_search"
    assert record["tools"][1]["error"] == "timeout"
    print("PASS test_trace_aggregates_tools_models_and_interrupt")
    return 0


if __name__ == "__main__":
    raise SystemExit(test_trace_aggregates_tools_models_and_interrupt())
