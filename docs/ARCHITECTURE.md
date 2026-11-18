# Harness 目录架构

## 分层

```text
src/
├─ core/              # 被两层以上同时依赖的内核：路径、配置、环境、日志、契约
├─ server/            # 传输层：FastAPI、SSE、历史会话、每用户会话与锁
│  └─ routes/         # chat（含 HITL resume）/ history / observability
├─ agent/             # 运行时层：组装（factory）与冷启动（bootstrap）
│  ├─ review/         # 阶段状态机、评审策略、路由、执行信号闸门 + rubrics.yaml
│  ├─ skills/         # 技能目录、同步/恢复、安装器、只读工具
│  ├─ memory/         # 三层记忆领域模型 + 记忆类中间件
│  ├─ middlewares/    # 横切：模型用量、工具追踪、工具摘要
│  ├─ prompts/        # 系统提示词与 AGENTS.md（不参与记忆存储）
│  ├─ subagents/      # 子 Agent YAML 配置
│  ├─ tools/          # Agent 侧工具：MCP 加载、图表、文档、HITL、联网
│  ├─ factory.py      # create_main_agent / precompute_agent_context
│  ├─ bootstrap.py    # 沙箱冷启动填充
│  └─ runtime.py      # 请求级上下文
├─ sandbox/           # 沙箱子系统：manager / holder / proxy / setup + 健康与熔断中间件
├─ observability/     # 单轮 trace（procuremind.turn.v1）与工具/模型指标
├─ infrastructure/    # 跨层基础设施适配：MongoDBStore
├─ mcp_server/        # MCP 协议适配：工具注册、HTTP 客户端、服务入口
│  └─ tools/          # 平台工具面（供应商/物资/申请/订单/库存/知识库）
├─ kb/                # RAG 领域：解析、切分、向量、BM25、召回、精排、引用
└─ __init__.py
```

顶层还有 `skills/`（技能内容数据，与 `src/agent/skills/` 代码分开）、`tests/`、`scripts/`、`evals/`。

## 依赖方向

```text
server ──► agent ──► mcp_server.tools ──► 平台 /api/**
   │          │
   │          ├──► sandbox（容器生命周期与文件后端）
   │          └──► infrastructure (MongoDBStore)
   └──► agent.factory / server.sessions 只做编排

core ◄── 所有层（只被依赖，不依赖任何业务层）
kb  ◄── mcp_server.tools.kb_tools（不入 Agent，只经 MCP 工具）
observability ◄── server.routes / mcp_server / sandbox
```

规则：

- `server` 只做协议与编排，不实现业务规则；
- `agent` 不直连数据库，所有业务读写经 MCP 工具；
- `mcp_server` 只做协议适配与参数校验，业务真相在平台；
- `kb` 是可独立测试的检索领域，不依赖 FastAPI/Agent；
- `infrastructure` 只放跨层适配器，不放业务逻辑；
- `core` 只能被依赖，不得 import 任何业务层（`agent` / `server` / `sandbox` / `kb`）。

## 运行产物

- `data/download/`：图表、报告等下载文件（已忽略，不提交）；
- `data/kb_state.json` / `data/bm25_stats.json`：RAG 增量状态（已忽略）；
- `logs/`：工具追踪、模型用量（已忽略）。

## 脚本目录

| 目录 | 用途 |
|---|---|
| `scripts/verify/s0..s7.py` | S0–S7 阶段门禁（`python -m scripts.verify.s0`） |
| `evals/{live,rag,security}/run.py` | 真机工具、RAG、安全评测（`python -m evals.rag.run`） |
| `scripts/smoke/` | SSE 链路、平台代理冒烟（`python -m scripts.smoke.sse_smoke`） |
| `scripts/seed/` | 语料生成与知识库入库（`python -m scripts.seed.kb_ingest`） |
| `scripts/dev/reset_demo.ps1` 等 | 运维/构建 |
| `evals/` | 评测语料与结果快照 |
| `qa/` | 一次性验收脚本与报告（仓库外或按需保留） |

## 已知例外

- 目前**没有**反向依赖：LLM 工厂在 `core/settings.py`，`kb/reranker.py` 直接用
  `from src.core.settings import get_llm`，不再依赖 Agent 层。
