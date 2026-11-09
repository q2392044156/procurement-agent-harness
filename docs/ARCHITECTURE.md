# Harness 目录架构

## 分层

```text
src/
├─ api_view/          # 传输层：FastAPI、SSE、历史会话、Agent 加载
├─ agent/             # 运行时层：建图、中间件、沙箱、子 Agent、提示词
│  ├─ prompts/        # 系统提示词与 AGENTS.md（不参与记忆存储）
│  ├─ memory/         # 三层记忆领域模型与 Keeper
│  ├─ middlewares/    # 横切：上下文、记忆、追踪、限流、RAG 守卫
│  ├─ backends/       # 沙箱/文件后端适配
│  ├─ tools/          # Agent 侧工具：MCP 客户端、图表、文档、技能读取
│  └─ subagents/      # 子 Agent YAML 配置
├─ mcp_server/        # MCP 协议适配：工具注册、HTTP 客户端、服务入口
│  └─ tools/          # 平台工具面（供应商/物资/申请/订单/库存/知识库）
├─ kb/                # RAG 领域：解析、切分、向量、BM25、召回、精排、引用
├─ infra/             # 跨层基础设施适配：MongoDBStore
├─ skills/            # 渐进披露的技能内容（SKILL.md 与资源）
└─ test/              # 不依赖外部服务的单元测试
```

## 依赖方向

```text
api_view ──► agent ──► mcp_server.tools ──► 平台 /api/**
    │           │
    └──────────►└──► infra (MongoDBStore)
kb ◄── mcp_server.tools.kb_tools
kb ◄── agent（仅通过 MCP 工具，不直接 import）
```

规则：

- `api_view` 只做协议与编排，不实现业务规则；
- `agent` 不直连数据库，所有业务读写经 MCP 工具；
- `mcp_server` 只做协议适配与参数校验，业务真相在平台；
- `kb` 是可独立测试的检索领域，不依赖 FastAPI/Agent；
- `infra` 只放跨层适配器，不放业务逻辑。

## 运行产物

- `data/download/`：图表、报告等下载文件（已忽略，不提交）；
- `data/kb_state.json` / `data/bm25_stats.json`：RAG 增量状态（已忽略）；
- `logs/`：工具追踪、模型用量（已忽略）。

## 脚本目录

| 目录 | 用途 |
|---|---|
| `scripts/verify_phase_*.py` | S0–S7 阶段门禁 |
| `scripts/eval_*.py` | RAG/在线工具评测 |
| `scripts/sse_smoke.py` 等 | HITL/代理冒烟 |
| `scripts/reset_demo.ps1` 等 | 运维/构建 |
| `evals/` | 评测语料与结果快照 |
| `qa/` | 一次性验收脚本与报告（仓库外或按需保留） |

## 已知例外

- `kb/reranker.py` 复用 `agent.config.get_llm` 做 LLM 精排；这是当前唯一的
  “领域 → Agent 配置”反向依赖，后续可把 LLM 工厂下沉到 `infra/llm.py`。
