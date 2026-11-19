# RAG（知识库检索）设计与运维

## 1. 分层

| 层 | 位置 | 职责 |
|---|---|---|
| 原文 | 平台 MinIO | 唯一文件真相，harness 不转存 |
| 元数据/可见性 | 平台 MySQL | `kb_document` + `visible-doc-ids`，检索前过滤 |
| 切片/向量 | Harness Qdrant | 可重建；payload 带 `doc_id/page/title/version` |

## 2. 入库（增量）

```
changed?since=上次同步时间
  → 过滤 PUBLISHED 且当前用户可见
  → documents/{id}/content 取预签名地址并下载
  → 解析（PDF 按页 / DOCX 按段落）
  → 切分（800 字符，120 重叠，按标点/段落回退）
  → bge-m3 向量化（1024 维，归一化）
  → 删除该文档旧切片 → 写入新切片（幂等 point id）
  → 更新 data/kb_state.json（since + 每文档 updatedAt）
```

归档/删除：同步时删除对应 `doc_id` 的全部切片；检索前再用 `visible-doc-ids` 兜底，避免越权召回。

## 3. 检索

```
用户问题
  → visible-doc-ids（当前身份）
  → bge-m3 向量
  → Qdrant filter: doc_id ∈ 可见集合
  → topK=8，score < 0.35 丢弃
  → 返回 text + 《标题》第N页
```

无命中时返回空结果，Agent 必须回答“知识库没有”，不得用通用知识补答。

## 8. 生产级增强（本轮）

**召回层**

- 自研 BM25：中文 bigram + 英文/数字词，文档侧长度归一化 TF、查询侧 IDF，写入 Qdrant named sparse vector `bm25`；
- dense + sparse 双路召回，Qdrant RRF 融合；
- 查询扩展：采购同义词（供应商/供方、账期/付款期限等），`KB_QUERY_EXPANSION` 控制。

**精排层**

- `KB_RERANKER=auto|fastembed|llm|none`：优先 fastembed cross-encoder（`BAAI/bge-reranker-v2-m3-int8`），不可用时回退 LLM 打分；
- 精排后按 `KB_RERANK_MIN_SCORE` 过滤，无相关片段直接返回空（拒答依据）；
- 按 `(doc_id,page,text)` 去重。

**生成层**

- 系统提示新增“知识库回答规则”：只依据片段、必须 `[《标题》第X页]`、无依据必须拒答；
- 流式结束前强制兜底：有片段但无引用时追加“依据：…”，检索为空时追加“知识库中没有找到依据”；
- `src/kb/grounding.py` 提供引用合法性校验，测试见 `tests/kb/test_grounding.py`。

**入库层**

- PDF 扫描页 OCR（PyMuPDF 渲染 + RapidOCR），PDF/DOCX 表格转 Markdown；
- 按页 + 标题/段落结构化切分，保留 `page/section`；
- MCP 启动后每 `KB_AUTO_SYNC_SECONDS` 秒轮询 `changed` 并增量入库（发布后最长 2 分钟生效）；
- 下载/平台请求 3 次重试，单文档失败不阻断整批，返回 `errors`；
- 新增 `/api/kb/documents/{id}/raw` 内部端点，容器内不依赖 MinIO 预签名 host；
- 新增 `.dockerignore`，避免 `.env`、状态文件进入镜像。

**测试**

```powershell
python -m pytest tests/kb/test_ingestion.py -q     # OCR/表格/结构化切分/BM25
python -m pytest tests/kb/test_grounding.py -q     # 引用/拒答校验
python -m pytest tests/kb/test_generation.py -q -m live  # 真实 Agent 引用与拒答
python -m evals.rag.run               # 混合检索 + 精排评测
```


P1 增强：

- **混合检索**：`combined = 0.75 × 向量分 + 0.25 × 字符 bigram 重合度`，
  权重由 `KB_LEXICAL_WEIGHT` 控制；
- **可见性前置过滤**：检索前取 `visible-doc-ids`，Qdrant filter 只查可见 `doc_id`；
  S4 门禁包含“只允许 doc 1 时不得召回 doc 2”的断言；
- **增量状态持久化**：容器内 `KB_STATE_FILE=/app/data/kb_state.json`，
  由 `kb-state` 卷持久化，重启不重复向量化。

## 4. 配置

| 变量 | 默认 | 说明 |
|---|---|---|
| `QDRANT_URL` | `http://localhost:6333` | 容器内为 `http://qdrant:6333` |
| `KB_COLLECTION` | `procurement_kb` | 集合名 |
| `KB_EMBEDDING_MODEL` | `BAAI/bge-m3` | 本地 CPU，首次下载约 2.2GB |
| `KB_TOP_K` / `KB_MIN_SCORE` | `8` / `0.40` | 召回数量与拒答阈值 |
| `HF_ENDPOINT` | `https://hf-mirror.com` | 国内镜像 |
| `HF_HOME` | 默认缓存目录 | 建议放在大磁盘 |

## 5. 本地启动

```powershell
docker run -d --name procuremind-qdrant -p 6333:6333 `
  -v procuremind-qdrant-data:/qdrant/storage qdrant/qdrant:latest

conda run -n procurement python -m scripts.seed.kb_ingest
conda run -n procurement python -m scripts.verify.s4
```

重建索引：删除 `data/kb_state.json`（或把 `since` 置为 1970）后重新执行入库；Qdrant 数据可随时丢弃重建。

## 6. 已知限制

- 语料：20 份采购制度 + 12 份工业物资技术/验收规范（IT、轴承、电机、数控、机器人、空压机、劳保、紧固件等）；50 问评测结果见 [EVAL_RAG.md](EVAL_RAG.md)；
- 未接 rerank 模型，仅用分数阈值（0.40 为当前语料标定值）；
- DOCX 无分页信息，页码固定为 1；扫描件 PDF 未做 OCR；
- 表格按纯文本抽取，结构可能丢失。

## 7. 验收口径（S4 已通过）

- 增量同步：新增/归档/删除均能反映到 Qdrant；
- 相关问题的 top 结果引用正确文档；
- 无关问题返回 0 条（拒答）；
- 引用文本包含《标题》与页码。
