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
| S7 | compose agent profile（Qdrant/Mongo/hf-cache）、一键脚本、部署文档 | 7/7（宿主运行态） | `c136584` + 平台 `74377a5` |

## S7 验证范围

已通过：

- `qdrant` 与 `mongo` 容器由 compose 启动，健康检查通过；
- 平台后端健康、Qdrant `/readyz` 200；
- MCP（宿主进程）51 个工具、真实平台调用成功；
- KB 检索指向 compose Qdrant，命中文档（20 份语料 / 23 切片）。

未完成：

- `agent` / `mcp` 镜像构建：Docker 内下载 torch（209MB）长时间停滞，已改为 Aliyun CPU wheel + 国内 pip 镜像，仍需在稳定网络或 CI 中完成；
- 因此 `demo-up.ps1 -Agent` 的容器化 agent/mcp 未做端到端启动验证；宿主进程方式已验证同一拓扑。

## 下一步

1. 在 CI 或稳定网络执行 `docker compose --profile agent build agent mcp`；
2. 云服务器部署并按 `docs/DEPLOYMENT.md` 验证；
3. 录制三分钟演示视频（脚本见平台 `docs/DEMO.md`）。
