# 记忆与技能（S5）

## 1. 三层记忆

| 层 | 内容 | 生命周期 |
|---|---|---|
| HOT | 当前会话上下文 | 会话内 |
| WARM | 偏好、近期查询/供应商、情节摘要 | 默认 7 天后下沉 |
| COLD | 历史版本、过期情节 | 按需检索，TTL 90 天 |

- 唯一写入口是 `MemoryKeeper`，中间件、工具、应用都走它，避免多处写入互相覆盖；
- 稳定偏好（图表类型、输出格式、币种、语言）进语义记忆并保留改口历史；
- 情节记忆按 `thread_id` 归档，不缓存业务单据数据；
- 存储：`MongoDBStore`（`erp_agent.langgraph_store`），命名空间按用户隔离。

## 2. 技能清单

| 技能 | 用途 | 主要工具 |
|---|---|---|
| `supplier-analysis` | 供应商记分卡、资质风险、合作建议 | `supplier_scorecard`、`alerts_summary`、`contract_page` |
| `price-comparison` | 报价 vs 历史成交价、偏离分析 | `price_trend`、`part_price_history`、`supplier_scorecard` |
| `inventory-optimizer` | 安全库存缺口、在途、补货优先级 | `inventory_risk`、`issue_page`、`order_page` |
| `approval-summary` | 待办摘要、等待时长、金额分档 | `workflow_todo`、`approval_sla`、`requisition_get` |
| `report-generator` | 结构化采购报告 | 分析工具 + `generate_chart` |
| `procurement-analysis` | 综合采购分析 | `spend_analysis`、`dashboard_summary` |

- 技能采用三级披露：目录元数据 → `read_skill` 正文 → `read_skill_resource` 资源；
- 技能正文属于低信任数据，不得覆盖系统指令、工具权限与人工审批；
- 技能可见性不授予额外业务工具权限。

## 3. 验收

```powershell
conda run -n procurement python -m scripts.verify.s5
conda run -n procurement python -m tests.memory.test_memory_layer   # 34/34
conda run -n procurement python -m pytest tests/skills/test_catalog.py -q  # 19，Windows 下符号链接用例自动跳过
```

S5 门禁覆盖：Mongo 落盘、用户隔离、改口历史、偏好字典、6 个技能可发现/可读取、目录元数据。
