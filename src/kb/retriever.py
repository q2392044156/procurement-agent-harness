"""检索：查询扩展 → dense+BM25 混合召回 → cross-encoder/LLM 精排。"""
from __future__ import annotations

import httpx

from src.kb.bm25 import load_stats, query_sparse
from src.kb.config import DEFAULT_TOP_K, ERP_BASE_URL, INTERNAL_TOKEN, MIN_SCORE, QUERY_EXPANSION, RERANK_MIN_SCORE
from src.kb.embedder import embed_query
from src.kb.reranker import rerank
from src.kb.store import search_hybrid

_SYNONYMS = {
    "供应商": ["供方", "厂商"],
    "账期": ["付款期限", "付款周期"],
    "质保": ["保修", "质量保证"],
    "采购申请": ["请购单"],
    "采购订单": ["订单"],
    "零部件": ["物料", "零件"],
    "库存": ["仓储", "存货"],
    "准入": ["资质", "资格"],
}


def _rewrite(query: str) -> str:
    if not QUERY_EXPANSION:
        return query
    additions: list[str] = []
    for term, synonyms in _SYNONYMS.items():
        if term in query:
            additions.extend(synonyms)
    return f"{query} {' '.join(additions)}" if additions else query


def _bigrams(text: str) -> set[str]:
    chars = [ch for ch in (text or "") if not ch.isspace()]
    return {chars[i] + chars[i + 1] for i in range(len(chars) - 1)}


def _lexical_score(query: str, text: str) -> float:
    query_grams = _bigrams(query)
    if not query_grams:
        return 0.0
    return len(query_grams & _bigrams(text)) / len(query_grams)


def _headers(user_id: str) -> dict:
    return {"X-Internal-Token": INTERNAL_TOKEN, "X-User-Id": user_id}


def visible_documents(user_id: str) -> list[dict]:
    response = httpx.get(
        f"{ERP_BASE_URL}/api/kb/visible-doc-ids", headers=_headers(user_id), timeout=30
    )
    response.raise_for_status()
    return response.json()["data"]


def search(query: str, user_id: str, top_k: int = DEFAULT_TOP_K) -> dict:
    documents = visible_documents(user_id)
    if not documents:
        return {
            "code": 0,
            "data": {
                "query": query,
                "results": [],
                "total": 0,
                "reason": "当前用户没有可见文档。",
            },
        }

    ids = [int(row["id"]) for row in documents]
    titles = {int(row["id"]): row.get("title") for row in documents}
    effective_query = _rewrite(query)
    dense_vector = embed_query(effective_query)
    sparse_indices, sparse_values = query_sparse(effective_query, load_stats())
    hits = search_hybrid(
        dense_vector, sparse_indices, sparse_values, ids, max(top_k * 4, 24)
    )

    candidates = []
    seen = set()
    for hit in hits:
        payload = hit.payload or {}
        key = (payload.get("doc_id"), payload.get("page"), str(payload.get("text", ""))[:80])
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            {
                "payload": payload,
                "rrf": float(getattr(hit, "score", 0.0) or 0.0),
                "lexical": _lexical_score(effective_query, payload.get("text", "")),
            }
        )

    scores = rerank(query, [item["payload"].get("text", "") for item in candidates])
    if scores is not None:
        for item, score in zip(candidates, scores):
            item["rerank"] = float(score)
        candidates = [
            item for item in candidates if item["rerank"] >= RERANK_MIN_SCORE
        ]
        candidates.sort(key=lambda item: item["rerank"], reverse=True)
    else:
        # 精排不可用时退回词法阈值，避免 RRF 噪声把所有片段都放行
        candidates = [
            item for item in candidates if item["lexical"] >= MIN_SCORE
        ]
        candidates.sort(key=lambda item: (item["lexical"], item["rrf"]), reverse=True)

    results = []
    for item in candidates[:top_k]:
        payload = item["payload"]
        doc_id = int(payload.get("doc_id"))
        page = payload.get("page")
        title = payload.get("title") or titles.get(doc_id)
        citation = f"《{title}》第{page}页" if page else f"《{title}》"
        results.append(
            {
                "docId": doc_id,
                "title": title,
                "page": page,
                "score": round(item.get("rerank", item.get("lexical", 0.0)), 4),
                "citation": citation,
                "text": payload.get("text", ""),
            }
        )

    return {"code": 0, "data": {"query": query, "results": results, "total": len(results)}}
