"""上传工业物资知识库语料并发布（幂等）。

用法：conda run -n procurement python scripts/seed_industrial_kb.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

from src.core.paths import PROJECT_ROOT as ROOT

PLATFORM = os.getenv("ERP_BASE_URL", "http://localhost:8080")
CORPUS = ROOT / "samples" / "kb_corpus_industrial"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def login() -> str:
    response = httpx.post(
        f"{PLATFORM}/api/v1/auth/login",
        json={"username": "admin", "password": "Admin@123"},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()["data"]["accessToken"]


def published_titles(headers: dict) -> set[str]:
    response = httpx.get(
        f"{PLATFORM}/api/v1/kb/documents",
        params={"size": 300},
        headers=headers,
        timeout=30,
    )
    return {row["title"] for row in response.json()["data"]["records"]}


def upload(headers: dict, path: Path, meta: dict, titles: set[str]) -> bool:
    if meta["title"] in titles:
        print(f"SKIP exists: {meta['title']}")
        return False
    content = path.read_bytes()
    presign = httpx.post(
        f"{PLATFORM}/api/v1/kb/uploads/presign",
        json={"fileName": path.name, "contentType": DOCX, "size": len(content)},
        headers=headers,
        timeout=30,
    )
    presign.raise_for_status()
    info = presign.json()["data"]
    put = httpx.put(
        info["uploadUrl"], content=content,
        headers={"Content-Type": DOCX}, timeout=120,
    )
    if put.status_code not in (200, 204):
        raise RuntimeError(f"upload failed {meta['title']}: {put.status_code}")
    created = httpx.post(
        f"{PLATFORM}/api/v1/kb/documents",
        json={
            "title": meta["title"],
            "category": meta["category"],
            "summary": meta["summary"],
            "tags": meta.get("tags", "工业物资"),
            "visibility": "ALL",
            "fileId": info["fileId"],
        },
        headers=headers,
        timeout=30,
    )
    created.raise_for_status()
    doc_id = created.json()["data"]["id"]
    httpx.patch(
        f"{PLATFORM}/api/v1/kb/documents/{doc_id}/status",
        json={"status": "PUBLISHED"},
        headers=headers,
        timeout=30,
    )
    titles.add(meta["title"])
    print(f"PUBLISHED {meta['title']} id={doc_id}")
    return True


def main() -> int:
    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    headers = {"Authorization": f"Bearer {login()}"}
    titles = published_titles(headers)
    added = 0
    for doc in manifest["documents"]:
        if upload(headers, CORPUS / doc["file"], doc, titles):
            added += 1
    print(f"added={added}, total published={len(published_titles(headers))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
