"""增量入库：平台 changed → 下载原文 → 解析/切分 → bge-m3 → Qdrant。"""
import json
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .chunker import chunk_pages
from .config import COLLECTION, ERP_BASE_URL, INTERNAL_TOKEN, STATE_FILE
from .embedder import dimension, embed_texts
from .parser import parse_document
from .store import count, delete_document, ensure_collection, upsert_chunks
from qdrant_client.http import models as qm


def _headers(user_id: str) -> dict:
    return {
        "X-Internal-Token": INTERNAL_TOKEN,
        "X-User-Id": user_id,
        "Content-Type": "application/json",
    }


def _platform(path: str, user_id: str, params: dict | None = None) -> dict:
    response = httpx.get(
        f"{ERP_BASE_URL}{path}", params=params, headers=_headers(user_id), timeout=60
    )
    response.raise_for_status()
    return response.json()


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def sync(user_id: str = "1") -> dict:
    """同步所有在 since 之后变化的文档，返回本次处理摘要。"""
    ensure_collection(dimension())
    state = _load_state()
    since = state.get("since") or "1970-01-01T00:00:00Z"
    processed: dict[str, str] = dict(state.get("documents") or {})

    changed = _platform("/api/kb/documents/changed", user_id, {"since": since})["data"]
    visible = {
        str(row["id"]): row
        for row in _platform("/api/kb/visible-doc-ids", user_id)["data"]
    }

    added = deleted = chunks = 0
    latest = since
    for row in changed:
        doc_id = int(row["id"])
        updated_at = str(row.get("updatedAt") or "")
        if updated_at > latest:
            latest = updated_at
        if processed.get(str(doc_id)) == updated_at:
            continue
        meta = visible.get(str(doc_id))
        if row.get("status") != "PUBLISHED" or not meta or int(row.get("deleted") or 0) == 1:
            delete_document(doc_id)
            processed[str(doc_id)] = updated_at
            deleted += 1
            continue

        content = _platform(f"/api/kb/documents/{doc_id}/content", user_id)["data"]
        download_url = content["downloadUrl"]
        file_name = content.get("fileName") or f"doc-{doc_id}.pdf"
        suffix = Path(file_name).suffix or ".pdf"
        with httpx.stream("GET", download_url, timeout=120, follow_redirects=True) as response:
            response.raise_for_status()
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
                temp_path = Path(handle.name)

        try:
            pages = parse_document(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

        pieces = chunk_pages(pages)
        if not pieces:
            delete_document(doc_id)
            continue

        vectors = embed_texts([piece["text"] for piece in pieces])
        point_ids = [
            str(uuid.uuid5(uuid.NAMESPACE_URL, f"kb:{doc_id}:{meta.get('currentVersion')}:{index}"))
            for index in range(len(pieces))
        ]
        points = [
            qm.PointStruct(
                id=point_ids[index],
                vector=vectors[index],
                payload={
                    "doc_id": doc_id,
                    "version": meta.get("currentVersion"),
                    "title": meta.get("title"),
                    "category": meta.get("category"),
                    "chunk_index": index,
                    "page": piece["page"],
                    "text": piece["text"],
                    "updated_at": updated_at,
                },
            )
            for index, piece in enumerate(pieces)
        ]
        delete_document(doc_id)
        upsert_chunks(points)
        added += 1
        chunks += len(points)
        processed[str(doc_id)] = updated_at

    _save_state({"since": latest or datetime.now(timezone.utc).isoformat(), "documents": processed})
    return {
        "since": since,
        "latest": latest,
        "documentsAdded": added,
        "documentsDeleted": deleted,
        "chunks": chunks,
        "collection": COLLECTION,
        "totalPoints": count(),
    }
