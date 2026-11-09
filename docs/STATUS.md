# 实现进度（S0–S7）

| 阶段 | 交付 | 门禁 | 提交 |
|---|---|---|---|
| S0 | 真机只读链路、MCP 令牌透传、阶段门禁 | 9/9 | `b7f909f` |
| S1 | 申请/审批/收货/仓库/出库/预算/合同/价格史只读工具 | 14/14 | `ca0f2fb` + 平台 `783053a` |
| S2 | 供应商记分卡、库存风险、花费分析、审批 SLA、价格趋势 | 7/7 | `59e21a0` + 平台 `e532f38` |
| S3 | 申请创建/提交/取消/转单、订单取消、幂等与 HITL | 10/10 | `43dcde3` + 平台 `72efe3b` |
| S4 | bge-m3 + Qdrant 知识库检索、引用、拒答 | 8/8 | `8d99c84` |
| S4.5 | 20 份语料 + 50 问评测（Top5 100%、拒答 100%） | PASS | `21516fc` |
| S5 | MongoDB 记忆闭环、6 个采购技能 | 9/9 | `fc9e702` |
| S6 | 真机评测 10/10、工具追踪、P95 97ms、Agent 单轮 | 6/6 | `e626492` |
| S7 | compose agent profile（Qdrant/Mongo/hf-cache）、镜像构建、一键脚本、部署文档 | 7/7（容器化） | `c136584` + 平台 `74377a5` |

## S7 验证范围（容器化）

已通过：

- `agent` / `mcp` 镜像构建完成（`docker build --network=host`，绕开 Docker 默认网络下 torch 下载停滞）；
- `agent`、`mcp`、`qdrant`、`mongo` 容器启动，`/health` 与 MCP SSE 正常；
- 平台 `AGENT_BASE_URL=http://agent:8000`，前端 SSE 代理 `PLATFORM PROXY: PASS`；
- 容器内 HITL：批准创建 1 单、拒绝 0 单，`SSE SMOKE: PASS`；
- KB 检索走 compose Qdrant（20 文档 / 23 切片）。

构建方式：

```powershell
cd procurement-agent-harness
.\scripts\build-images.ps1      # docker build --network=host
cd ..\smart-procurement-platform
.\scripts\demo-up.ps1 -Agent
```

## P1 完善（本轮）

- RAG：向量 + 字符 bigram 混合检索；可见性前置过滤断言；`kb-state` 卷持久化增量状态；
- 工具：统一 `errorType/retryable`；写工具支持 `idempotency_key`、结构化 `items`、`verified` 标记、单次 20 条上限；
- 可观测：trace 10MB 轮转、`byThread` 聚合、模型 token/成本估算；
- 安全：`/api/chat` 每用户限流、提示注入边界、记忆 PII 脱敏、MongoDBStore 唯一索引修复、seccomp 安全沙箱；
- 评测：live 场景 10→31（31/31），S4 9/9、S5 10/10、S6 7/7；
- CI：新增 `.github/workflows/harness-ci.yml`。

## 下一步

1. 云服务器部署并按 `docs/DEPLOYMENT.md` 验证；
2. 录制三分钟演示视频（脚本见平台 `docs/DEMO.md`）。
