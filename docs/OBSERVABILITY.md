# 可观测性

Harness 提供两层可观测性：工具/模型调用级 trace，以及一次用户请求的 Turn 级汇总。全部写入本地 JSONL，不依赖外部 APM。

## 1. 工具调用 trace

`logs/tool_trace.jsonl`：

| 字段 | 说明 |
|---|---|
| `trace_id` | 当前 Turn 的 trace ID |
| `request_id` | 单次工具调用 ID |
| `thread_id` / `user_id` | 会话与用户 |
| `tool` / `args_keys` | 工具名与参数键（不记录参数值） |
| `status` / `error` | ok / error 与错误摘要 |
| `duration_ms` / `result_len` | 耗时与结果长度 |
| `ts` | 时间戳 |

## 2. Turn 级 trace

`logs/turn_trace.jsonl`，每个 SSE 请求一条：

| 字段 | 说明 |
|---|---|
| `trace_id` | 32 位十六进制，兼容 OpenTelemetry trace_id 形态 |
| `thread_id` / `user_id` | 会话与用户 |
| `status` | `ok` / `error` / `interrupted` |
| `duration_ms` | 整个 Turn 耗时 |
| `interrupts` | HITL 中断次数 |
| `model_calls` / `input_tokens` / `output_tokens` | 模型调用与 token |
| `tool_calls` / `tool_errors` / `tools` | 工具调用列表与错误 |

`logs/model_usage.jsonl` 记录每次模型调用的 token、模型名、耗时与估算标记。

## 3. HTTP API

需要 `X-Internal-Token`：

| 接口 | 内容 |
|---|---|
| `GET /api/observability/summary` | 工具调用、成功率、P50/P95、模型 token/成本、Turn 数/中断数 |
| `GET /api/observability/turns?limit=50` | 最近的 Turn trace |
| `GET /api/observability/threads/{thread_id}` | 指定会话的 Turn、工具、模型时间线 |
| `GET /api/observability/errors?limit=20` | 最近工具错误 |

示例：

```powershell
$token = (Get-Content .env | Select-String '^AGENT_INTERNAL_TOKEN=').ToString().Split('=',2)[1]
Invoke-RestMethod http://localhost:8000/api/observability/summary `
  -Headers @{ 'X-Internal-Token' = $token; 'X-User-Id' = '1' }
```

## 4. HTML 看板

```powershell
python -m scripts.dev.observability_report --api http://localhost:8000
```

输出 `logs/observability.html`，包含：

- 工具调用数、成功率、P95；
- 模型调用、输入/输出 token、估算成本；
- Turn 数、中断数、Turn P95；
- 按工具统计；
- 最近 Turn 的 trace_id、thread、状态、工具/模型调用和耗时。

`docs/screenshots/07-observability.png` 是看板截图。

## 5. 已验证

- 普通 chat：生成 Turn trace，工具调用与模型调用归集正确；
- HITL：Turn 状态为 `interrupted`，中断次数为 1；
- `GET /api/observability/summary`、`/turns`、`/threads/{id}` 返回一致；
- HTML 看板可离线打开。

## 6. 限制

- JSONL 本地文件适合演示和单实例；多实例/生产应接入 OpenTelemetry Collector、Langfuse 或 ClickHouse；
- 没有在线告警、采样和长期存储；
- token 为估算值，流式 DeepSeek 不返回 usage 时会标记 `estimated=true`。
