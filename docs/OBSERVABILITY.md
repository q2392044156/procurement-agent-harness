# 评测与可观测（S6）

## 1. 工具调用追踪

`ToolTraceMiddleware` 与 MCP 工具包装器共用 `record_tool_call`：MCP 工具在
`load_mcp_tools` 返回前被包装，因此主 Agent、子 Agent、直接调用都会写入
`logs/tool_trace.jsonl`（可用 `TOOL_TRACE_FILE` 覆盖）。

| 字段 | 说明 |
|---|---|
| `request_id` | 单次调用 ID，便于串联日志 |
| `thread_id` / `user_id` | 会话与用户 |
| `tool` / `args_keys` | 工具名与参数键（不记录参数值，避免敏感数据落盘） |
| `status` / `error` | ok / error 与错误摘要 |
| `duration_ms` / `result_len` | 耗时与结果长度 |
| `ts` | 时间戳 |

指标命令：

```powershell
conda run -n procurement python -m src.agent.metrics
```

输出：调用数、成功率、P50/P95/max、按工具分布、最近错误。

P1 增强：

- 追踪文件超过 10MB 自动轮转为 `tool_trace.jsonl.1`；
- 指标额外输出 `byThread`（按会话聚合）；
- `ModelUsageMiddleware` 记录每次模型调用的输入/输出 token，指标输出
  `modelCalls / inputTokens / outputTokens / estimatedCostUsd / byModel`；
- 单价可用 `MODEL_INPUT_PRICE_PER_M` / `MODEL_OUTPUT_PRICE_PER_M` 覆盖。

## 2. 真机评测

`scripts/eval_live.py` 不经过 LLM，直接通过 MCP 调真实平台，覆盖 10 个只读场景：

| 场景 | 断言 |
|---|---|
| supplier_page / part_page | 返回真实记录 |
| requisition_page | 申请总数 ≥ 1 |
| budget_list | 4 个部门预算 |
| contract_page | 合同 ≥ 2 |
| inventory_risk | MOUSE-USB-001 净缺口 > 0 |
| supplier_scorecard | 含 amount 字段 |
| spend_analysis | 总花费 > 0 |
| kb_search | 供应商准入问题命中 |
| inventory_warning | 返回 code=0 |

结果写入 `evals/live/summary.json`（含每条耗时）。

## 3. 端到端 Agent 单轮

`scripts/live_agent_turn.py` 用真实 DeepSeek + MCP + 主 Agent 中间件跑一轮
“库存预警 + 补货建议”，并把工具调用写入 trace，用于验证：

- 主 Agent 会委派给分析师子 Agent；
- 子 Agent 的工具调用同样被追踪；
- 回复基于真实库存数据（当前 19 / 安全库存 20）。

## 4. 门禁

```powershell
conda run -n procurement python scripts/verify_phase_s6.py
```

判定：

- 真机 10/10 通过；
- Agent 单轮有非空回复；
- trace 至少 1 条，成功率 ≥ 95%，P95 ≤ 20s。

## 5. 当前结果

- 真机评测：**10/10**，平均 69ms，最大 152ms（本地 Docker）；
- Agent 单轮：成功返回库存分析与补货建议；
- 追踪：主/子 Agent 工具调用入库，指标可复现。

## 6. 后续可扩展

- 将 trace 写入 Mongo/OTel，接入 Grafana；
- 评测集扩充到 50 条业务场景（当前 10 条真机 + 既有 LLM 评测）；
- 增加成本统计（token 用量按模型单价折算）。
