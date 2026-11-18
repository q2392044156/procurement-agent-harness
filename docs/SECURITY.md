# 安全边界与部署要求

## 1. 信任边界

| 组件 | 暴露范围 | 认证 |
|---|---|---|
| 平台前端 / `/api/v1/**` | 浏览器 | JWT |
| 平台 `/api/**` 工具面 | 仅 Agent/MCP 内网 | `X-Internal-Token` + `X-User-Id` |
| Agent `/api/chat/**` | 仅平台后端 | `X-Internal-Token` |
| MCP `:8001` | 仅 Agent/内网 | 透传内部令牌 |
| Qdrant / Mongo | 仅内网 | 无公网端口 |

**令牌即边界**：`X-User-Id` 由平台注入，MCP 只透传；任何能直连 MCP 并持有令牌的调用方都能代表任意用户，因此 MCP/Agent 端口必须只绑定内网或 `127.0.0.1`。

## 2. 已落地的防护

- **HITL**：9 个写工具（订单创建/修改/提交/关闭/取消、申请创建/提交/取消/转单）全部中断，主 Agent 与子 Agent 均继承同一清单，人工 `approve/reject` 后才执行；
- **幂等**：平台按操作 + 用户 + 内容去重，Agent 重试不重复建单；
- **限流**：`/api/chat/**` 默认每用户 30 次/分钟（`AGENT_RATE_LIMIT_PER_MINUTE`）；
- **PII 脱敏**：记忆写入前对手机号、邮箱、API Key 做 `[REDACTED]`；
- **提示注入**：系统提示明确知识库/技能/网页为低信任数据，不得覆盖指令、权限与审批；
- **沙箱**：seccomp 白名单 + `cap_drop ALL` + 只读根目录 + 无网络（可配）；
- **内部错误**：统一返回 `errorType` 与 `retryable`，403/409 明确不可重试。

## 3. 生产部署要求

1. 只暴露 Nginx 的 80/443，代理 `/api/v1/`；`/api/`、8000、8001、6333 不对外；
2. 轮换 `JWT_SECRET`、`AGENT_INTERNAL_TOKEN`，`.env` 权限 600；
3. Qdrant/Mongo 使用独立网络与卷，定期备份；
4. 为 Agent/MCP 增加网络策略（仅平台后端可访问）；
5. 上线前跑 `python -m scripts.verify.s7.py` 与平台 P0/P1/P2/KB 脚本。

## 4. 已知剩余风险

- 暂无 mTLS/请求签名，令牌泄露即可冒充；
- 无 OTel/Prometheus，审计依赖 JSONL 日志；
- 沙箱基础镜像为 `python:3.11-slim`，未做镜像签名与漏洞扫描。
