"""S6 阶段门禁：真机评测 + 工具追踪 + 指标。

1. 运行 scripts/eval_live.py（10 个真机只读场景，不经 LLM）
2. 运行 scripts/live_agent_turn.py（真实 LLM + MCP + 记忆/技能中间件）
3. 汇总 logs/tool_trace.jsonl：调用数、成功率、P50/P95

用法：conda run -n procurement python scripts/verify_phase_s6.py
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    return ok


def run(script: str, timeout: int = 420) -> tuple[int, str]:
    process = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    output = (process.stdout or "") + (process.stderr or "")
    return process.returncode, output


def main() -> int:
    trace_file = ROOT / "logs" / "tool_trace.jsonl"
    if trace_file.exists():
        trace_file.unlink()

    code, output = run("eval_live.py", 300)
    check("live tool eval", code == 0, f"exit={code}")
    summary_path = ROOT / "evals" / "live" / "summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        check("live eval coverage",
              summary["passed"] == summary["cases"] and summary["cases"] >= 30,
              f"{summary['passed']}/{summary['cases']} avg={summary['avgLatencyMs']}ms")
    else:
        check("live eval coverage", False, "summary.json missing")

    code, output = run("live_agent_turn.py", 420)
    reply_chars = 0
    for line in output.splitlines():
        if line.startswith("REPLY_CHARS:"):
            try:
                reply_chars = int(line.split(":", 1)[1].strip())
            except ValueError:
                reply_chars = 0
    check("agent turn completed", reply_chars >= 100, f"replyChars={reply_chars} exit={code}")

    from src.agent.metrics import summarize

    metrics = summarize()
    check("tool trace recorded", metrics["exists"] and metrics["calls"] >= 1,
          f"calls={metrics['calls']} tools={list(metrics['byTool'])}")
    check("tool success rate", metrics["successRate"] >= 0.95,
          f"successRate={metrics['successRate']} errors={metrics['errors']}")
    check("tool latency p95", 0 < metrics["p95Ms"] <= 20000,
          f"p50={metrics['p50Ms']}ms p95={metrics['p95Ms']}ms max={metrics['maxMs']}ms")
    check("model usage recorded", metrics["modelCalls"] >= 1 and metrics["inputTokens"] > 0,
          f"calls={metrics['modelCalls']} in={metrics['inputTokens']} out={metrics['outputTokens']} "
          f"cost=${metrics['estimatedCostUsd']}")

    failed = [name for name, ok, _ in RESULTS if not ok]
    print()
    print(f"PHASE S6: {'PASS' if not failed else 'FAIL'} ({len(RESULTS) - len(failed)}/{len(RESULTS)})")
    if failed:
        print("failed:", ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
