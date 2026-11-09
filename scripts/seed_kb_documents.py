"""把示例文档与评测语料上传到平台知识库并发布（幂等）。

用法：conda run -n procurement python scripts/seed_kb_documents.py
"""
import json
import os
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = os.getenv("ERP_BASE_URL", "http://localhost:8080")
SAMPLES = ROOT / "samples" / "knowledge"
if not SAMPLES.exists():
    SAMPLES = ROOT.parent / "smart-procurement-platform" / "samples" / "knowledge"
CORPUS = ROOT / "samples" / "kb_corpus"
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
        params={"size": 200},
        headers=headers,
        timeout=30,
    )
    return {row["title"] for row in response.json()["data"]["records"]}


def upload(headers: dict, path: Path, content_type: str, meta: dict, titles: set[str]) -> bool:
    if meta["title"] in titles:
        print(f"SKIP exists: {meta['title']}")
        return False
    data = path.read_bytes()
    presign = httpx.post(
        f"{PLATFORM}/api/v1/kb/uploads/presign",
        json={"fileName": path.name, "contentType": content_type, "size": len(data)},
        headers=headers,
        timeout=30,
    ).json()["data"]
    put = httpx.put(
        presign["uploadUrl"],
        content=data,
        headers={"Content-Type": content_type},
        timeout=120,
    )
    if put.status_code not in (200, 204):
        raise RuntimeError(f"upload failed {meta['title']}: {put.status_code}")
    created = httpx.post(
        f"{PLATFORM}/api/v1/kb/documents",
        json={
            "title": meta["title"],
            "category": meta["category"],
            "summary": meta["summary"],
            "tags": meta.get("tags", "评测语料"),
            "visibility": "ALL",
            "fileId": presign["fileId"],
        },
        headers=headers,
        timeout=30,
    ).json()
    doc_id = created["data"]["id"]
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
    headers = {"Authorization": f"Bearer {login()}"}
    titles = published_titles(headers)

    upload(
        headers,
        SAMPLES / "internal-procurement-policy.docx",
        DOCX,
        {"title": "内部采购管理制度", "category": "POLICY",
         "summary": "采购申请、审批权限、供应商选择与订单执行的管理制度", "tags": "采购,制度,审批"},
        titles,
    )
    upload(
        headers,
        SAMPLES / "supplier-admission-policy.pdf",
        "application/pdf",
        {"title": "供应商准入与绩效评价管理办法", "category": "SUPPLIER",
         "summary": "供应商准入条件、资质要求、绩效评价与退出机制", "tags": "供应商,准入,评价"},
        titles,
    )

    manifest_path = CORPUS / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for doc in manifest["documents"]:
            upload(
                headers,
                CORPUS / doc["file"],
                DOCX,
                {"title": doc["title"], "category": doc["category"], "summary": doc["summary"]},
                titles,
            )

    print("published docs:", len(published_titles(headers)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
