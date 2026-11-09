"""检索：按用户可见文档过滤，返回带引用的切片。"""
import httpx

from .config import DEFAULT_TOP_K, ERP_BASE_URL, INTERNAL_TOKEN, LEXICAL_WEIGHT, MIN_SCORE
from .embedder import embed_query
from .store import search as vector_search


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
            "data": {"query": query, "results": [], "total": 0, "reason": "当前用户没有可见文档"},
        }

    ids = [int(row["id"]) for row in documents]
    titles = {int(row["id"]): row.get("title") for row in documents}
    hits = vector_search(embed_query(query), ids, max(top_k * 3, 20))

    scored = []
    for hit in hits:
        payload = hit.payload or {}
        vector_score = float(hit.score)
        lexical = _lexical_score(query, payload.get("text", ""))
        combined = (1 - LEXICAL_WEIGHT) * vector_score + LEXICAL_WEIGHT * lexical
        scored.append((combined, vector_score, payload))
    scored.sort(key=lambda item: item[0], reverse=True)

    results = []
    for combined, _vector_score, payload in scored:
        if combined < MIN_SCORE:
            continue
        doc_id = int(payload.get("doc_id"))
        page = payload.get("page")
        title = payload.get("title") or titles.get(doc_id)
        citation = f"《{title}》第{page}页" if page else f"《{title}》"
        results.append(
            {
                "docId": doc_id,
                "title": title,
                "page": page,
                "score": round(combined, 4),
                "citation": citation,
                "text": payload.get("text", ""),
            }
        )
        if len(results) >= top_k:
            break
    return {
        "code": 0,
        "data": {"query": query, "results": results, "total": len(results)},
    }
