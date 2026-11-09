"""知识库 MCP 工具：检索、取文档、引用。"""
import asyncio
import json
import os

import httpx
from fastmcp import FastMCP

from .config import ERP_BASE_URL, INTERNAL_TOKEN
from .retriever import search as kb_search_sync
from .retriever import visible_documents


def _current_user_id() -> str:
    try:
        from fastmcp.server.dependencies import get_http_headers

        headers = {str(k).lower(): str(v) for k, v in (get_http_headers() or {}).items()}
        return headers.get("x-user-id") or os.getenv("KB_DEFAULT_USER_ID", "1")
    except Exception:
        return os.getenv("KB_DEFAULT_USER_ID", "1")


def _internal_headers(user_id: str) -> dict:
    return {"X-Internal-Token": INTERNAL_TOKEN, "X-User-Id": user_id}


def register_kb_tools(mcp: FastMCP):
    """注册知识库检索工具到 MCP Server"""

    @mcp.tool()
    async def kb_search(query: str, top_k: int = 8) -> str:
        """在内部知识库中做语义检索，返回带页码引用的片段。

        Args:
            query: 自然语言问题，例如“供应商准入需要哪些资质”
            top_k: 返回片段数，默认8

        Returns:
            JSON：results 中每项含 title、page、score、citation、text；无依据时 results 为空
        """
        user_id = _current_user_id()
        result = await asyncio.to_thread(kb_search_sync, query, user_id, top_k)
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def kb_get_document(id: int) -> str:
        """获取知识库文档的元数据与预签名下载地址（需当前用户可见）。

        Args:
            id: 文档ID

        Returns:
            JSON：fileName、downloadUrl、expiresIn
        """
        user_id = _current_user_id()
        response = httpx.get(
            f"{ERP_BASE_URL}/api/kb/documents/{id}/content",
            headers=_internal_headers(user_id),
            timeout=30,
        )
        try:
            return json.dumps(response.json(), ensure_ascii=False, indent=2)
        except Exception:  # noqa: BLE001
            return json.dumps({"code": response.status_code, "message": response.text[:300]},
                              ensure_ascii=False)

    @mcp.tool()
    async def kb_cite(doc_id: int, page: int = 1) -> str:
        """生成文档引用文本（标题 + 页码），用于回答中标注来源。

        Args:
            doc_id: 文档ID
            page: 页码，默认1

        Returns:
            JSON：citation（如“《内部采购管理制度》第3页”）
        """
        user_id = _current_user_id()
        documents = await asyncio.to_thread(visible_documents, user_id)
        match = next((row for row in documents if int(row["id"]) == int(doc_id)), None)
        if not match:
            return json.dumps({"code": 404, "message": "文档不存在或不在当前可见范围内"},
                              ensure_ascii=False)
        title = match.get("title")
        return json.dumps(
            {"code": 0, "data": {"citation": f"《{title}》第{page}页", "docId": doc_id, "page": page}},
            ensure_ascii=False,
        )
