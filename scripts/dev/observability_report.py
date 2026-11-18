"""生成只读可观测性看板：logs/observability.html。

用法：
    python scripts/observability_report.py
"""
from __future__ import annotations

import argparse
import html
import os
import sys
from pathlib import Path

import httpx

from src.core.paths import PROJECT_ROOT as ROOT

from src.observability.metrics import summarize  # noqa: E402
from src.observability.trace import read_turns  # noqa: E402


def esc(value) -> str:
    return html.escape(str(value if value is not None else "-"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default=os.getenv("OBSERVABILITY_API", ""),
                        help="从 Agent HTTP API 读取，例如 http://localhost:8000")
    args = parser.parse_args()
    if args.api:
        base = args.api.rstrip("/")
        token = os.getenv("AGENT_INTERNAL_TOKEN", "")
        headers = {"X-Internal-Token": token, "X-User-Id": "1"}
        summary = httpx.get(f"{base}/api/observability/summary",
                            headers=headers, timeout=30).json()["data"]
        turns = list(reversed(httpx.get(f"{base}/api/observability/turns",
                                       params={"limit": 20},
                                       headers=headers, timeout=30).json()["data"]))
    else:
        summary = summarize()
        turns = list(reversed(read_turns(20)))
    cards = [
        ("工具调用", summary["calls"]),
        ("成功率", f"{summary['successRate'] * 100:.1f}%"),
        ("P95", f"{summary['p95Ms']} ms"),
        ("模型调用", summary["modelCalls"]),
        ("输入 / 输出 Token", f"{summary['inputTokens']} / {summary['outputTokens']}"),
        ("估算成本", f"${summary['estimatedCostUsd']}"),
        ("有效 Turn", summary["turns"]),
        ("中断 Turn", summary["interruptedTurns"]),
        ("Turn P95", f"{summary['p95TurnMs']} ms"),
    ]
    card_html = "".join(
        f'<div class="card"><div class="label">{esc(label)}</div><div class="value">{esc(value)}</div></div>'
        for label, value in cards
    )
    tool_rows = "".join(
        f"<tr><td>{esc(name)}</td><td>{row['calls']}</td><td>{row['errors']}</td></tr>"
        for name, row in summary["byTool"].items()
    )
    turn_rows = "".join(
        "<tr>"
        f"<td>{esc(row.get('trace_id'))}</td>"
        f"<td>{esc(row.get('thread_id'))}</td>"
        f"<td>{esc(row.get('user_id'))}</td>"
        f"<td>{esc(row.get('status'))}</td>"
        f"<td>{esc(row.get('tool_calls'))}</td>"
        f"<td>{esc(row.get('model_calls'))}</td>"
        f"<td>{esc(row.get('duration_ms'))} ms</td>"
        f"<td>{esc(row.get('interrupts'))}</td>"
        "</tr>"
        for row in turns
    )
    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ProcureMind Agent Observability</title>
<style>
  body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f5f7fb; color: #1f2937; }}
  header {{ padding: 28px 40px; background: #111827; color: white; }}
  header h1 {{ margin: 0; font-size: 24px; }}
  header p {{ margin: 8px 0 0; color: #9ca3af; font-size: 13px; }}
  main {{ padding: 24px 40px 40px; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 14px; margin-bottom: 24px; }}
  .card {{ background: white; border-radius: 10px; padding: 16px 18px; box-shadow: 0 1px 3px rgba(15,23,42,.08); }}
  .label {{ color: #6b7280; font-size: 12px; }}
  .value {{ font-size: 24px; font-weight: 650; margin-top: 6px; }}
  h2 {{ font-size: 16px; margin: 24px 0 10px; }}
  table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 1px 3px rgba(15,23,42,.08); }}
  th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid #eef2f7; font-size: 13px; }}
  th {{ background: #f9fafb; color: #374151; font-weight: 600; }}
  code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
  .muted {{ color: #6b7280; font-size: 12px; margin-top: 10px; }}
</style>
</head>
<body>
<header>
  <h1>ProcureMind Agent Observability</h1>
  <p>工具调用 · 模型用量 · Turn 延迟 · HITL 中断 · Trace ID</p>
</header>
<main>
  <div class="cards">{card_html}</div>
  <h2>按工具统计</h2>
  <table><thead><tr><th>工具</th><th>调用</th><th>错误</th></tr></thead><tbody>{tool_rows or '<tr><td colspan="3">暂无数据</td></tr>'}</tbody></table>
  <h2>最近 Turn</h2>
  <table><thead><tr><th>Trace ID</th><th>Thread</th><th>User</th><th>状态</th><th>工具</th><th>模型</th><th>耗时</th><th>中断</th></tr></thead>
  <tbody>{turn_rows or '<tr><td colspan="8">暂无数据</td></tr>'}</tbody></table>
  <p class="muted">数据来源：logs/tool_trace.jsonl、logs/model_usage.jsonl、logs/turn_trace.jsonl；生成时间：{esc(summary.get("traceFile"))}</p>
</main>
</body>
</html>"""
    target = ROOT / "logs" / "observability.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(document, encoding="utf-8")
    print(f"written {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
