"""Qdrant 存储：dense + BM25 sparse 混合检索、删除、统计。"""
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from .config import COLLECTION, QDRANT_URL

DENSE = "dense"
SPARSE = "bm25"

_client: QdrantClient | None = None


def client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=QDRANT_URL, timeout=30)
    return _client


def ensure_collection(dim: int) -> None:
    if client().collection_exists(COLLECTION):
        return
    client().create_collection(
        COLLECTION,
        vectors_config={DENSE: qm.VectorParams(size=dim, distance=qm.Distance.COSINE)},
        sparse_vectors_config={SPARSE: qm.SparseVectorParams()},
    )
    try:
        client().create_payload_index(
            COLLECTION, field_name="doc_id", field_schema=qm.PayloadSchemaType.KEYWORD
        )
    except Exception:
        pass


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


def upsert_chunks(points: list[qm.PointStruct], batch_size: int = 64) -> None:
    for start in range(0, len(points), batch_size):
        client().upsert(COLLECTION, points=points[start:start + batch_size])


def count() -> int:
    if not client().collection_exists(COLLECTION):
        return 0
    return client().count(COLLECTION, exact=True).count


def all_texts() -> list[str]:
    texts: list[str] = []
    offset = None
    while True:
        points, offset = client().scroll(
            COLLECTION, limit=256, offset=offset, with_payload=["text"], with_vectors=False
        )
        texts.extend(str((point.payload or {}).get("text") or "") for point in points)
        if offset is None:
            break
    return texts


def _filter(visible_ids: list[int]) -> qm.Filter:
    return qm.Filter(
        must=[qm.FieldCondition(key="doc_id", match=qm.MatchAny(any=[int(i) for i in visible_ids]))]
    )


def search_hybrid(
    dense_vector: list[float],
    sparse_indices: list[int],
    sparse_values: list[float],
    visible_ids: list[int],
    limit: int,
) -> list:
    if not visible_ids:
        return []
    flt = _filter(visible_ids)
    prefetch = [
        qm.Prefetch(query=dense_vector, using=DENSE, filter=flt, limit=limit),
    ]
    if sparse_indices:
        prefetch.append(
            qm.Prefetch(
                query=qm.SparseVector(indices=sparse_indices, values=sparse_values),
                using=SPARSE,
                filter=flt,
                limit=limit,
            )
        )
    response = client().query_points(
        collection_name=COLLECTION,
        prefetch=prefetch,
        query=qm.FusionQuery(fusion=qm.Fusion.RRF),
        limit=limit,
        with_payload=True,
    )
    return list(response.points)
