# Harness 项目树重构计划

> 目标：**在不改变运行行为的前提下**，把 `procurement-agent-harness/` 整理成「目录即模块、文件名即职责」的结构。
> 约束：HTTP 路径、SSE 事件名、MCP 工具名、Agent 行为**一律不变**——重构只动 `import` 和图上的装配位置，不动任何契约。

---

## 0. 现状诊断

### 0.1 量化基线

| 指标 | 现状 |
|---|---|
| 纳入版本管理的文件 | 225 |
| `src/` 下文件 | 129（其中测试 14、技能数据 15、代码 100） |
| 顶层目录 | `src/` `scripts/` `evals/` `docs/` `samples/` `data/` `logs/` + 5 个配置文件 |
| 最大目录 | `src/agent/` 62 个文件、8 个子目录、根上还平铺 12 个模块 |
| `__pycache__` 目录（磁盘） | 21 个（虽已 gitignore，但出现在 IDE 树里） |
| 明确死代码 | 3 个文件（见 0.3） |
| 反向依赖 | `src/kb/reranker.py` → `src/agent/config.py`（ARCHITECTURE.md 已自认唯一例外） |

### 0.2 三个具体病灶

**病灶 A：测试和代码混住**
`src/test/` 14 个文件，CI 用 `python -m src.test.test_memory_layer` 跑，导致测试成了「运行时包的一部分」。而且 `src/test/` 里还夹了 `measure_skill_prompt.py`（基准脚本）、`test_memory_layer.py`（被 `test_memory_integration.py` 当夹具库 import）。

**病灶 B：`src/agent/` 是杂物间**
一个目录同时装着 6 种关注点：

| 关注点 | 文件 |
|---|---|
| 全局配置/日志/环境 | `config.py` `log_utils.py` `env_utils.py` |
| 数据契约 | `schema.py` |
| 组装 | `main_agent.py`（426 行，还塞了沙箱 bootstrap） |
| 评审域 | `harness.py` `review_policy.py` `jev_router.py` `middlewares/review_gate.py` |
| 技能域 | `progressive_skills.py` `middlewares/skills_sync.py` `middlewares/user_skills_restore.py` `tools/skill_management.py` |
| 记忆域 | `memory/*` + `middlewares/{warm_memory,memory_update,memory_consolidation}.py`（域内代码被劈成两半） |

**病灶 C：命名不达意 / 同名不同物**

| 现名 | 实际是什么 | 问题 |
|---|---|---|
| `src/api_view/` | HTTP 接入层 | “view”让人以为是模板层；里面还有个 `api/` 子包 |
| `src/api_view/api/` | 路由 | api_view/api 双层重复 |
| `src/agent/backends/` | 沙箱容器生命周期 | backend 太泛，6 个文件全是 sandbox |
| `src/infra/` | 只有 1 个 `mongodb_store.py` | 单文件撑不起一层 |
| `src/agent/harness.py` | 四阶段状态机 + 评审 DSL | 以项目名命名模块，等于没命名 |
| `src/skills/` | **数据**（SKILL.md） | 与代码同处 `src/`，`progressive_skills.py` 反而是代码 |
| `src/agent/tools/web_fetch.py` | 抓网页 **+ 安装技能**（575 行） | 一个文件两个职责，`install_skill` 藏在 fetch 里 |
| `src/agent/tools/hitl_tools.py` 等 | 后缀 `_tools` 冗余 | 在 `tools/` 包里不必再叫 tools |

### 0.3 死代码（0 引用，已核实）

| 文件 | 证据 | 处置 |
|---|---|---|
| `src/agent/middleware_config.py` | `git grep middleware_config` 只命中自身；且 `from deepagents.middleware import SummarizationToolMiddleware` 这个 API 已在用的版本里不存在 | 删除 |
| `src/agent/mcp_tools_bean.py` | 只命中自身；`ANALYST_TOOL_PATTERNS` 的逻辑已由 `subagents/configs/*.yaml` 取代 | 删除 |
| `src/agent/tools/assign_skill.py` | 工具从未注册进 `create_main_agent`，只有 `skills/main/skill-management/SKILL.md` 文档提到 | 删除（或并入技能域后按需恢复） |
| `src/agent/middlewares/context_injection.py` | 已注册进栈（`main_agent.py:366`），但 `before_agent`/`after_agent` 均 `return None`，上下文实际由 system_prompt 注入 | 确认无副作用后从栈中摘除并删除 |

`_load_skills_prompt`（`main_agent.py:137`）不是死代码——被 `src/test/measure_skill_prompt.py` 当基准调用，随之迁入 `tests/` 后一起决定去留。

### 0.4 工具链基线（本机实测）

| 项 | 实测 |
|---|---|
| `python` / `python3` | `C:\Users\Administrator\AppData\Local\Microsoft\WindowsApps\python.exe`（Store 占位符，`python -c` 直接报「系统找不到指定的路径」，**不可用**）|
| `uv` | `0.12.11`，已装 `cpython-3.12.14` → 用 `uv venv .venv --python 3.12` 建隔离环境 |
| 仓库内 venv | 无；`.venv/` 已在 `.gitignore:19` 里，可直接建 |
| `docker` | CLI 可用，但 `docker images` 为空 → `docker build` / 沙箱验收先标「需环境」，不阻塞提交 |
| CI 可用命令 | `python -m compileall -q src`、`python -m src.test.test_memory_layer`、`python -m src.test.test_progressive_skills`、`python scripts/test_rag_grounding.py` |

依赖安装说明：`requirements.txt` 里 `sentence-transformers`（→PyTorch）与 OCR/PDF 系（`pymupdf` `pdfplumber` `rapidocr`）只在 KB 检索链路用，基线门禁不碰它们，P0 先装轻量集合，避免为了跑 3 个测试拖一个 torch。

---

## 1. 目标结构

```
procurement-agent-harness/
├── src/                          # 只放可 import 的代码
│   ├── core/                     # 共享内核：谁都可以依赖，它不依赖任何人
│   │   ├── settings.py           #   ← agent/config.py（常量部分）
│   │   ├── llm.py                #   ← agent/config.py 的 get_llm
│   │   ├── env.py                #   ← agent/env_utils.py
│   │   ├── logging.py            #   ← agent/log_utils.py
│   │   ├── paths.py              #   新增：PROJECT_ROOT / SKILLS_DIR / PROMPTS_DIR 唯一来源
│   │   └── contracts.py          #   ← agent/schema.py
│   ├── server/                   # 接入层：只做 HTTP/SSE 翻译
│   │   ├── main.py               #   ← api_view/web_main.py
│   │   ├── settings.py           #   ← api_view/web_config.py
│   │   ├── sessions.py           #   ← api_view/agent_loader.py
│   │   └── routes/{chat,history,observability}.py
│   ├── agent/                    # 运行时：只做装配
│   │   ├── factory.py            #   ← main_agent.py（去掉 bootstrap）
│   │   ├── bootstrap.py          #   ← main_agent.py 的 _upload_project_to_sandbox / bootstrap_sandbox
│   │   ├── runtime.py            #   ← runtime_context.py
│   │   ├── prompts/{main.py, AGENTS.md}
│   │   ├── subagents/{loader.py, configs/*.yaml}
│   │   ├── middlewares/          #   只留跨域横切：tools_summarization.py, model_usage.py
│   │   ├── tools/                #   charts.py documents.py sandbox_files.py hitl.py
│   │   │                         #   mcp_loader.py memory.py web_search.py web_fetch.py
│   │   ├── review/               #   评审域（自洽）
│   │   │   ├── phase.py          #   ← harness.py
│   │   │   ├── policy.py         #   ← review_policy.py
│   │   │   ├── router.py         #   ← jev_router.py
│   │   │   ├── gate.py           #   ← middlewares/review_gate.py
│   │   │   └── rubrics.yaml      #   ← harness_config.yaml
│   │   ├── skills/               #   技能域（自洽）
│   │   │   ├── catalog.py        #   ← progressive_skills.py
│   │   │   ├── sync.py           #   ← middlewares/skills_sync.py
│   │   │   ├── restore.py        #   ← middlewares/user_skills_restore.py
│   │   │   ├── installer.py      #   ← web_fetch.py 里的 install_skill
│   │   │   └── tools.py          #   ← tools/skill_management.py
│   │   └── memory/               #   记忆域（补齐中间件，收拢）
│   │       ├── config.py keeper.py extractor.py scoring.py namespaces.py types.py
│   │       └── middlewares/{warm.py, update.py, consolidation.py}
│   ├── sandbox/                  #   ← agent/backends（容器生命周期是一个独立子系统）
│   │   ├── manager.py holder.py proxy.py setup.py opensandbox.py seccomp.json
│   │   ├── health_middleware.py  #   ← middlewares/sandbox_health.py
│   │   └── breaker_middleware.py #   ← middlewares/sandbox_breaker.py
│   ├── observability/            #   ← agent/observability.py + agent/metrics.py
│   │   ├── trace.py
│   │   └── metrics.py
│   ├── kb/                       #   不动（结构已内聚）
│   ├── mcp_server/               #   不动（结构已内聚）
│   └── infrastructure/
│       └── mongo_store.py        #   ← infra/mongodb_store.py
├── skills/                       # ← src/skills（数据，与代码彻底分开）
├── tests/                        # ← src/test + scripts/test_*（与 src 平级）
│   ├── support/fakes.py
│   ├── memory/ skills/ review/ sandbox/ observability/ kb/ tools/
│   └── integration/
├── scripts/
│   ├── verify/                   #   verify_s0..s7.py
│   ├── seed/                     #   kb_ingest seed_kb_documents seed_industrial_kb generate_*
│   ├── smoke/                    #   sse_smoke platform_proxy_smoke
│   └── dev/                      #   live_agent_turn observability_report reset_demo build-images
├── evals/                        #   business/ review_routing/ live/ security/ rag/
└── docs/ samples/ data/
```

**顶层 `src/` 从 7 个目录变成 8 个**，但语义边界清晰了：`core`（被依赖）→ `server`（入）→ `agent`（编排）→ `sandbox` / `kb` / `mcp_server`（能力）→ `infrastructure` / `observability`（横切）。

### 1.1 关键取舍（附理由）

| 决策 | 选择 | 理由 |
|---|---|---|
| 是否把 `src` 改名为 `harness`/`app` | **不改** | 294 处 `src.` 引用 + Dockerfile `COPY src src` + CI `python -m src.test.*`；改名零可读性收益，风险却最大。真正难看的是 `src/` **里面** |
| 技能代码放哪 | `src/agent/skills/`（代码）+ 根 `skills/`（数据） | 避免 `src/skills`（数据）与 `src/agent/skills`（代码）在**同一前缀**下撞名 |
| 技能数据放哪（已确认） | 仓库根 `skills/` | 行业通行的「内容资产」位置：Rasa Mantle 的骨架是 `agent.yml + integrations.yml + skills/`，`gh skill` / `npx skills` 的发现规则字面就是 `skills/*/SKILL.md`（任意非隐藏深度）。Claude Code 用 `.claude/skills/`，但那是它自身工具链的槽位，本项目 `create_deep_agent(skills=None)` + 自研 catalog 不读它。判断标准是「谁编辑、谁消费」：这 15 个 SKILL.md 是业务内容、被拷进沙箱而非被 `import` |
| `install_skill` 的宿主机写入 | **删除**（方案 a），只写沙箱 + Store | `web_fetch.py:479-483` 现在往 `SKILLS_DIR` 写，curated（git 跟踪）与 installed（运行产生）混在同一目录。挪到根目录后这个隐患会被放大：仓库工作区变脏，容器内该层也不可写。Store 已是真相源（`_persist_installed_skill`，`web_fetch.py:494`），`UserSkillsRestoreMiddleware` 负责回灌沙箱，宿主机那份是纯历史包袱 |
| `sandbox` 是否留在 `agent/` 下 | 提到顶层 | 被 server（维护协程）、tools（写文件）、agent（backend）三方使用，不是 agent 私有 |
| `memory` 是否提到顶层 | 留在 `agent/memory/` | 只被 agent 的中间件与 memory 工具使用，属于 agent 运行时 |
| 测试目录怎么组织 | 按域分 `tests/memory` `tests/review` … | 与 `src/agent/*` 域一一对应，改哪个域跑哪个目录 |
| `harness.py` 改名 | `review/phase.py` | 项目本身叫 harness，模块再叫 harness 无法自解释；它实际是「阶段状态机」 |

---

## 2. 迁移映射表（文件级）

### 2.1 共享内核

| 现 | 新 |
|---|---|
| `src/agent/config.py` | `src/core/settings.py` + `src/core/llm.py` |
| `src/agent/env_utils.py` | `src/core/env.py` |
| `src/agent/log_utils.py` | `src/core/logging.py` |
| `src/agent/schema.py` | `src/core/contracts.py`（`AgentState/Phase/Plan/ReviewResult` 拆到 `src/agent/review/state.py`） |
| —（散落 3 处 `PROJECT_ROOT / "src" / "skills"`） | `src/core/paths.py` |

### 2.2 接入层

| 现 | 新 |
|---|---|
| `src/api_view/web_main.py` | `src/server/main.py` |
| `src/api_view/web_config.py` | `src/server/settings.py` |
| `src/api_view/agent_loader.py` | `src/server/sessions.py` |
| `src/api_view/api/chat.py` | `src/server/routes/chat.py` |
| `src/api_view/api/history.py` | `src/server/routes/history.py` |
| `src/api_view/api/observability.py` | `src/server/routes/observability.py` |

入口命令随之变化：`python -m src.api_view.web_main` → `python -m src.server.main`
（影响：`Dockerfile` CMD、`WSL_START.md`、`README.md`）

### 2.3 运行时

| 现 | 新 |
|---|---|
| `src/agent/main_agent.py` | `src/agent/factory.py` + `src/agent/bootstrap.py` |
| `src/agent/runtime_context.py` | `src/agent/runtime.py` |
| `src/agent/observability.py` | `src/observability/trace.py` |
| `src/agent/metrics.py` | `src/observability/metrics.py` |
| `src/agent/harness.py` + `harness_config.yaml` | `src/agent/review/phase.py` + `review/rubrics.yaml` |
| `src/agent/review_policy.py` | `src/agent/review/policy.py` |
| `src/agent/jev_router.py` | `src/agent/review/router.py` |
| `src/agent/middlewares/review_gate.py` | `src/agent/review/gate.py` |
| `src/agent/progressive_skills.py` | `src/agent/skills/catalog.py` |
| `src/agent/middlewares/skills_sync.py` | `src/agent/skills/sync.py` |
| `src/agent/middlewares/user_skills_restore.py` | `src/agent/skills/restore.py` |
| `src/agent/middlewares/warm_memory.py` | `src/agent/memory/middlewares/warm.py` |
| `src/agent/middlewares/memory_update.py` | `src/agent/memory/middlewares/update.py` |
| `src/agent/middlewares/memory_consolidation.py` | `src/agent/memory/middlewares/consolidation.py` |
| `src/agent/middlewares/sandbox_health.py` | `src/sandbox/health_middleware.py` |
| `src/agent/middlewares/sandbox_breaker.py` | `src/sandbox/breaker_middleware.py` |
| `src/agent/middleware_config.py` | **删除** |
| `src/agent/mcp_tools_bean.py` | **删除** |
| `src/agent/middlewares/context_injection.py` | **删除**（先摘栈） |

### 2.4 工具

| 现 | 新 |
|---|---|
| `tools/mcp_client.py` | `tools/mcp_loader.py` |
| `tools/chart_generator.py` | `tools/charts.py` |
| `tools/document_generator.py` | `tools/documents.py` |
| `tools/download_sandbox_file.py` | `tools/sandbox_files.py` |
| `tools/hitl_tools.py` | `tools/hitl.py` |
| `tools/memory_tools.py` | `tools/memory.py` |
| `tools/web_search.py` | `tools/web_search.py`（不动） |
| `tools/web_fetch.py`（575 行） | `tools/web_fetch.py`（只留 `web_fetch`）+ `skills/installer.py`（`install_skill` 及沙箱校验/持久化 3 个私有函数） |
| `tools/skill_management.py` | `skills/tools.py` |
| `tools/assign_skill.py` | **删除** |

### 2.5 沙箱 / 存储

| 现 | 新 |
|---|---|
| `agent/backends/custom_opensandbox.py` | `sandbox/opensandbox.py` |
| `agent/backends/sandbox_manager.py` | `sandbox/manager.py` |
| `agent/backends/sandbox_holder.py` | `sandbox/holder.py` |
| `agent/backends/sandbox_proxy.py` | `sandbox/proxy.py` |
| `agent/backends/sandbox_setup.py` | `sandbox/setup.py` |
| `agent/backends/seccomp.json` | `sandbox/seccomp.json` |
| `infra/mongodb_store.py` | `infrastructure/mongo_store.py` |

### 2.6 数据

| 现 | 新 |
|---|---|
| `src/skills/**`（15 个文件） | `skills/**`（仓库根） |

需要同步改的 8 处硬编码/文档：
`agent/main_agent.py:33`、`agent/main_agent.py:129`（沙箱内 `cp /workspace/src/src/skills`）、`tools/web_fetch.py:31`、`test/measure_skill_prompt.py:20`、`Dockerfile`（`COPY src src` → 追加 `COPY skills skills`）、`.dockerignore`、`docs/PROGRESSIVE_SKILLS.md:34`、`skills/main/skill-management/SKILL.md:62`。

**顺带简化**：`_upload_project_to_sandbox`（`main_agent.py:38`）是把整个 `PROJECT_ROOT` 打包解到容器 `/workspace/src`，所以技能挪到根之后在容器里自动落在 `/workspace/src/skills/`，`bootstrap_sandbox` 的 cp 从 `/workspace/src/src/skills/.` 变成 `/workspace/src/skills/.`——路径反而更短，且不再依赖 `src/` 的嵌套层级。

### 2.7 测试

| 现 | 新 |
|---|---|
| `src/test/test_memory_layer.py` | `tests/memory/test_memory_layer.py`（`FakeStore/Msg` → `tests/support/fakes.py`） |
| `src/test/test_memory_integration.py` | `tests/memory/test_memory_integration.py` |
| `src/test/test_progressive_skills.py` | `tests/skills/test_catalog.py` |
| `src/test/test_hybrid_review.py` | `tests/review/test_review_chain.py` |
| `src/test/test_jev_router.py` | `tests/review/test_router.py` |
| `src/test/test_sandbox_lifecycle.py` | `tests/sandbox/test_lifecycle.py` |
| `src/test/test_observability.py` | `tests/observability/test_trace.py` |
| `src/test/test_web_search.py` | `tests/tools/test_web_search.py` |
| `src/test/agent_test.py` | `tests/integration/test_agent_smoke.py` |
| `src/test/test_all_tools.py` | `tests/integration/test_all_tools.py` |
| `src/test/test_mcp.py` | `tests/integration/test_mcp.py` |
| `src/test/test_business_eval.py` | `tests/integration/test_business_eval.py` |
| `src/test/measure_skill_prompt.py` | `tests/tools/measure_skill_prompt.py` |
| `scripts/test_hitl_scope.py` | `tests/review/test_hitl_scope.py` |
| `scripts/test_rag_grounding.py` | `tests/kb/test_grounding.py` |
| `scripts/test_rag_ingestion.py` | `tests/kb/test_ingestion.py` |
| `scripts/test_rag_generation.py` | `tests/kb/test_generation.py`（标 `@pytest.mark.live`） |

配套：新增 `pyproject.toml`

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
markers = ["live: 需要真实 LLM / 平台 / Docker"]
```

一次性删掉 4 处 `sys.path.insert(...)` 胶水（`agent_test.py:9`、`test_all_tools.py:9`、`test_mcp.py:10`、`measure_skill_prompt.py`）。

### 2.8 脚本

| 现 | 新 |
|---|---|
| `scripts/verify_phase_s0..s7.py` | `scripts/verify/s0..s7.py` |
| `scripts/kb_ingest.py` `seed_kb_documents.py` `seed_industrial_kb.py` `generate_kb_corpus.py` `generate_industrial_corpus.py` | `scripts/seed/` |
| `scripts/sse_smoke.py` `platform_proxy_smoke.py` | `scripts/smoke/` |
| `scripts/live_agent_turn.py` `observability_report.py` `reset_demo.ps1` `build-images.ps1` | `scripts/dev/` |
| `scripts/eval_live.py` `eval_rag.py` `security_eval.py` | `evals/{live,rag,security}/run.py`（让 `evals/` 同时收脚本与结果） |

---

## 3. 分阶段执行

每一阶段都可独立提交、独立回滚，**每阶段结束必须绿灯**。

### P0 基线（30 min）

1. `git switch -c refactor/tree`，确认 `git status` 干净。
2. 记录基线：`python -m compileall -q src`；逐条跑 CI 现有 3 个测试；记录哪些 `verify_phase_s*` 能跑（依赖 Docker/Mongo 的记为「需环境」）。
3. 清磁盘噪音（均未纳入版本管理，不影响运行）：21 个 `__pycache__`、`.idea/`、`src/download/`、`.pytest_cache`。`logs/*.jsonl` 是先前的观测数据，**保留**用于 P4 前后对比。
4. 产出：基线清单写进本文件附录。

**验收**：`git status` 干净；基线测试结果记录在案。

### P1 死代码清理（30 min，零结构变动）

1. 删 `middleware_config.py`、`mcp_tools_bean.py`、`assign_skill.py`。
2. `main_agent.py` 摘掉 `ContextInjectionMiddleware`（第 311、366 行）并删文件——**单独一个 commit**，便于行为回归时精确回退。
3. `_load_skills_prompt` 暂留（等 P2 测试迁移后一起处理）。

**验收**：`compileall` 通过；CI 3 个测试通过；起服务跑一轮对话，`phase/token/tool_*` 事件与基线一致。

### P2 测试与脚本分离（1 h，低风险）

1. `git mv src/test tests`（保留历史），再按 2.7 拆子目录。
2. 新增 `tests/support/fakes.py`、`tests/conftest.py`、`pyproject.toml`。
3. `git mv scripts/test_*.py tests/...`。
4. 改 CI 3 条命令 → `python -m pytest tests/memory tests/skills -q` 等。
5. 删 `sys.path.insert` 胶水。

**验收**：`python -m pytest -q` 全绿（与 P0 基线同集合）；`python -m compileall -q src tests` 通过。

### P3 数据与代码分离（1 h，中风险）

1. `git mv src/skills skills`。
2. 新增 `src/core/paths.py`，把 3 处 `PROJECT_ROOT / "src" / "skills"` 归一。
3. 改 `main_agent.py:129` 沙箱内路径 → `cp -r /workspace/src/skills/. /skills/`。
4. 改 `Dockerfile`（`COPY skills skills`）、`.dockerignore`、文档 2 处。
5. **方案 a**：删掉 `install_skill` 的宿主机写入（`tools/web_fetch.py:479-483` 的 `host_skills_dir` / `host_target` 那几行），只保留沙箱 `/skills/custom/<name>/`（`web_fetch.py:487`）+ Store 持久化（`_persist_installed_skill`）。顺带把 `tools/` 里已无用的 `SKILLS_DIR` 引用改成 `core/paths.SKILLS_DIR`（仍有读取方需要它）。

**验收**：本地起 agent → 触发一次需要沙箱的请求 → 沙箱内 `ls /skills` 有内容；`SkillCatalog(SKILLS_DIR).index()` 能列出 15 个技能；**装一次技能后 `git status` 仍干净**（方案 a 的硬门禁）；`docker build` 成功。

### P4 重命名与分层（2–3 h，中高风险，机械但有量）

1. 按 2.2–2.5、2.8 做 `git mv`（**先移动文件，再改 import**，避免半途不可运行）。
2. 写一次性 codemod（`scripts/dev/rewrite_imports.py`，跑完即删）：按映射表替换 `from src.x.y import`、`from ..x import`、`from .x import`，处理相对深度的变化。
3. 手工核对这几处「字符串路径」——codemod 抓不到：
   - `agent/harness.py:33` 的 `Path(__file__).parent / "harness_config.yaml"`（随文件一起移动，保持相对关系）
   - `server/main.py:14`、`mcp_server/server_main.py:10` 的 `sys.path.insert(..., '..','..')`（深度变了，改用 `core.paths.PROJECT_ROOT`）
   - `agent/main_agent.py:129` 沙箱 `cp` 路径
4. 改入口：`Dockerfile` CMD、`WSL_START.md:44,51`、`README.md:157`。

**验收**：`compileall` + `pytest -q` 全绿；`python -m src.server.main` 能起；`python -m src.mcp_server.server_main` 能起；`scripts/smoke/sse_smoke.py` 通过；一次真实对话（含一次写操作中断 + resume）。

### P5 内核抽取与反向依赖修复（可选，2 h）

1. `config.py` 拆成 `core/settings.py`（常量）+ `core/llm.py`（`get_llm`）。
2. `kb/reranker.py:40` 的 `from src.agent.config import get_llm` → `from src.core.llm import get_llm`，ARCHITECTURE.md 的「已知例外」消失。
3. `schema.py` 拆 `core/contracts.py`（对外的 Pydantic 模型）与 `agent/review/state.py`（`AgentState/Phase/Plan/ReviewResult`）。

**验收**：`python -c "import src.kb.reranker"` 不再间接加载 agent 包；pytest 全绿。

---

## 4. 风险清单与对策

| 风险 | 为什么会发生 | 对策 |
|---|---|---|
| **相对导入深度错位** | `from ...agent.x` 的 `.` 数量随目录深度变化，`compileall` 只查语法不查解析 | codemod 后跑一个「逐模块 import」冒烟脚本（对无外部依赖的模块 `importlib.import_module`），把 `ImportError` 在提交前暴露 |
| **字符串路径失效** | 沙箱内 `cp /workspace/src/src/skills`、`__file__.parent / "harness_config.yaml"` 都不是 import | 在 P3/P4 验收里强制跑一次「沙箱 bootstrap + 一轮对话」，不只看单测 |
| **`-m` 入口改名** | 启动命令写死在 Dockerfile/WSL/README 里 | 已核实：`my_project2/` 全仓除 `harness/docs` 外**无** `api_view` / `web_main` 引用，平台侧不直接调 harness 入口。需同步改的只有 `Dockerfile` CMD、`WSL_START.md:44,51`、`README.md:157`、`docs/ARCHITECTURE.md:7,26,35` |
| **循环导入** | 把 `settings` 抽到 `core` 后，`core` 若反向 import `agent` 就成环 | 定死依赖方向：`core` 零内部依赖；用 `python -c "import src.core.settings"` 验证 |
| **测试夹具跨文件共享** | `test_memory_integration.py` 直接 `from src.test.test_memory_layer import FakeStore` | P2 里先抽 `tests/support/fakes.py` 再改两处引用，避免迁移顺序踩空 |
| **一次性大 diff 不可 review** | 294 处 import 一起改 | 严格按 P1→P5 分 5 个 commit，每个 commit 单独可回滚（`git revert <P4>` 即回到可运行态） |
| **技能数据迁移破坏镜像** | `Dockerfile` 只 `COPY src src` | P3 里 `docker build` + 容器内 `ls /skills` 作为硬门禁 |

---

## 5. 明确不动的部分

- **所有 HTTP 路径**（`/api/chat/stream`、`/api/chat/{id}/resume`、`/api/chat/{id}/state`、`/api/chat/{id}/history`、`/api/download/*`、`/health`）
- **所有 SSE 事件名**（`token` `tool_start` `tool_args` `tool_result` `tool_end` `phase` `todo_update` `review_result` `hitl_approval` `done`）
- **所有 MCP 工具名**（`order_create` … `kb_search`，共 10 组）
- **中间件的注册顺序**（P1 只摘掉 no-op 的那一个，其余顺序不变）
- **`src/kb/` 与 `src/mcp_server/` 的内部结构**（已内聚，只改它们的 import 头）
- **Mongo 集合名、Store namespace、`harness_config.yaml` 的键名**

---

## 6. 预期收益（量化）

| 指标 | 现在 | 之后 |
|---|---|---|
| `src/` 下文件 | 129 | ~100（测试 14 出、技能 15 出、死代码 3 删） |
| `src/agent/` 根目录平铺模块 | 12 | 3（`factory.py` `bootstrap.py` `runtime.py`） |
| `src/agent/` 子目录 | 8（关注点混装） | 7（每目录一个域） |
| 单文件最大职责数 | `web_fetch.py` 2 个、`main_agent.py` 3 个 | 每文件 1 个 |
| `sys.path.insert` 胶水 | 4 处（测试）+ 2 处（入口） | 0 |
| 反向依赖 | 1（kb → agent） | 0 |
| SRP 违规的目录名 | `api_view` `backends` `infra` `harness.py` | 无 |

---

## 附录 A：P0 基线记录

分支 `refactor/tree`，起点 `4c8c029`（main）。环境：`.venv`（uv + cpython-3.12.14），`PYTHONPATH=.`。

| 门禁 | 命令 | 结果 |
|---|---|---|
| 语法 | `python -m compileall -q src` | PASS（exit 0） |
| 记忆层 | `python -m src.test.test_memory_layer` | PASS 34/34 |
| 渐进披露 | `python -m src.test.test_progressive_skills` | PASS 19 tests（1 SKIP：本机无 symlink 权限） |
| RAG 引用 | `python scripts/test_rag_grounding.py` | PASS（3 asserts） |

未安装 `sentence-transformers`（→PyTorch）、`pymupdf` `pdfplumber` `rapidocr`：KB 重链路不参与任何门禁，装了只会拖慢循环。
容器相关验证（`verify_phase_s*`、`sse_smoke.py`、`docker build`）需要 Docker 镜像 + 平台在跑，本机 `docker images` 为空 → 记为**需环境**，不作为本次提交的阻塞门禁；纯代码门禁全部可在 `.venv` 内跑完。
