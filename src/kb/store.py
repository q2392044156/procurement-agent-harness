"""Qdrant 存储：集合管理、按文档删除、检索。"""
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from .config import COLLECTION, QDRANT_URL

_client: QdrantClient | None = None


def client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=QDRANT_URL, timeout=30)
    return _client


def ensure_collection(dim: int) -> None:
    if not client().collection_exists(COLLECTION):
        client().create_collection(
            COLLECTION,
            vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
        )


def delete_document(doc_id: int) -> None:
    if not client().collection_exists(COLLECTION):
        return
    client().delete(
        COLLECTION,
        points_selector=qm.FilterSelector(
            filter=qm.Filter(
                must=[qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=int(doc_id)))]
            )
        ),
    )


def upsert_chunks(points: list[qm.PointStruct]) -> None:
    if points:
        client().upsert(COLLECTION, points=points)


def count() -> int:
    if not client().collection_exists(COLLECTION):
        return 0
    return client().count(COLLECTION, exact=True).count


def search(vector: list[float], visible_ids: list[int], limit: int) -> list:
    if not visible_ids:
        return []
    flt = qm.Filter(
        must=[qm.FieldCondition(key="doc_id", match=qm.MatchAny(any=[int(i) for i in visible_ids]))]
    )
    response = client().query_points(
        collection_name=COLLECTION,
        query=vector,
        query_filter=flt,
        limit=limit,
        with_payload=True,
    )
    return list(response.points)
