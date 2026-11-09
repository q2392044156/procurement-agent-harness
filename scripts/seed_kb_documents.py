"""把 samples/knowledge 下的示例文档上传到平台知识库并发布（幂等）。

用法：conda run -n procurement python scripts/seed_kb_documents.py
"""
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = os.getenv("ERP_BASE_URL", "http://localhost:8080")
SAMPLES = ROOT / "samples" / "knowledge"
if not SAMPLES.exists():
    SAMPLES = ROOT.parent / "smart-procurement-platform" / "samples" / "knowledge"

DOCS = [
    {
        "file": "internal-procurement-policy.docx",
        "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "title": "内部采购管理制度",
        "category": "POLICY",
        "summary": "采购申请、审批权限、供应商选择与订单执行的管理制度",
        "tags": "采购,制度,审批",
    },
    {
        "file": "supplier-admission-policy.pdf",
        "content_type": "application/pdf",
        "title": "供应商准入与绩效评价管理办法",
        "category": "SUPPLIER",
        "summary": "供应商准入条件、资质要求、绩效评价与退出机制",
        "tags": "供应商,准入,评价",
    },
]


def main() -> int:
    login = httpx.post(
        f"{PLATFORM}/api/v1/auth/login",
        json={"username": "admin", "password": "Admin@123"},
        timeout=20,
    ).json()
    token = login["data"]["accessToken"]
    headers = {"Authorization": f"Bearer {token}"}

    existing = httpx.get(
        f"{PLATFORM}/api/v1/kb/documents",
        params={"size": 100},
        headers=headers,
        timeout=20,
    ).json()
    titles = {row["title"] for row in existing["data"]["records"]}

    for doc in DOCS:
        path = SAMPLES / doc["file"]
        if not path.exists():
            print(f"SKIP missing file: {path}")
            continue
        if doc["title"] in titles:
            print(f"SKIP exists: {doc['title']}")
            continue
        data = path.read_bytes()
        presign = httpx.post(
            f"{PLATFORM}/api/v1/kb/uploads/presign",
            json={"fileName": path.name, "contentType": doc["content_type"], "size": len(data)},
            headers=headers,
            timeout=20,
        ).json()["data"]
        upload = httpx.put(
            presign["uploadUrl"],
            content=data,
            headers={"Content-Type": doc["content_type"]},
            timeout=60,
        )
        if upload.status_code not in (200, 204):
            print(f"FAIL upload {doc['title']}: {upload.status_code}")
            return 1
        created = httpx.post(
            f"{PLATFORM}/api/v1/kb/documents",
            json={
                "title": doc["title"],
                "category": doc["category"],
                "summary": doc["summary"],
                "tags": doc["tags"],
                "visibility": "ALL",
                "fileId": presign["fileId"],
            },
            headers=headers,
            timeout=20,
        ).json()
        doc_id = created["data"]["id"] if "data" in created else created.get("id")
        httpx.patch(
            f"{PLATFORM}/api/v1/kb/documents/{doc_id}/status",
            json={"status": "PUBLISHED"},
            headers=headers,
            timeout=20,
        )
        print(f"PUBLISHED {doc['title']} id={doc_id}")

    final = httpx.get(
        f"{PLATFORM}/api/v1/kb/documents",
        params={"status": "PUBLISHED", "size": 100},
        headers=headers,
        timeout=20,
    ).json()
    print("published docs:", len(final["data"]["records"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
