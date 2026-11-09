"""
HTTP 基础客户端模块
httpx AsyncClient 单例（连接池、超时），封装 GET/POST/PUT/PATCH/DELETE

错误统一为：
{"code":<status>, "message":..., "data":..., "errorType":..., "retryable":bool}
"""
import os
from typing import Optional

import httpx

from .server_config import ERP_BASE_URL, HTTP_TIMEOUT, HTTP_MAX_CONNECTIONS

_ERROR_TYPES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation",
    429: "rate_limited",
    500: "server_error",
    502: "bad_gateway",
    503: "unavailable",
    504: "timeout",
}
_RETRYABLE = {429, 500, 502, 503, 504}


class ERPHttpClient:
    """ERP 后端 HTTP 客户端单例"""

    _instance: Optional["ERPHttpClient"] = None
    _client: Optional[httpx.AsyncClient] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=ERP_BASE_URL,
                timeout=httpx.Timeout(HTTP_TIMEOUT),
                limits=httpx.Limits(
                    max_connections=HTTP_MAX_CONNECTIONS,
                    max_keepalive_connections=10,
                ),
                headers={"Content-Type": "application/json"},
            )
        return self._client

    def _headers(self, extra: Optional[dict] = None) -> dict:
        merged = self._forward_headers()
        if extra:
            merged.update({str(k): str(v) for k, v in extra.items()})
        return merged

    async def get(self, path: str, params: Optional[dict] = None,
                  headers: Optional[dict] = None) -> dict:
        if params:
            params = {k: v for k, v in params.items() if v is not None}
        response = await self.client.get(path, params=params, headers=self._headers(headers))
        return self._handle_response(response)

    async def post(self, path: str, json_data: Optional[dict] = None,
                   params: Optional[dict] = None, headers: Optional[dict] = None) -> dict:
        if params:
            params = {k: v for k, v in params.items() if v is not None}
        response = await self.client.post(
            path, json=json_data, params=params, headers=self._headers(headers)
        )
        return self._handle_response(response)

    async def put(self, path: str, json_data: Optional[dict] = None,
                  params: Optional[dict] = None, headers: Optional[dict] = None) -> dict:
        if params:
            params = {k: v for k, v in params.items() if v is not None}
        response = await self.client.put(
            path, json=json_data, params=params, headers=self._headers(headers)
        )
        return self._handle_response(response)

    async def patch(self, path: str, params: Optional[dict] = None,
                    headers: Optional[dict] = None) -> dict:
        if params:
            params = {k: v for k, v in params.items() if v is not None}
        response = await self.client.patch(path, params=params, headers=self._headers(headers))
        return self._handle_response(response)

    async def delete(self, path: str, headers: Optional[dict] = None) -> dict:
        response = await self.client.delete(path, headers=self._headers(headers))
        return self._handle_response(response)

    def _forward_headers(self) -> dict:
        """将 Agent 建立 MCP 会话时携带的内部身份继续传给 Spring。"""
        incoming = {}
        try:
            from fastmcp.server.dependencies import get_http_headers

            incoming = get_http_headers() or {}
        except Exception:
            pass
        lower = {str(k).lower(): str(v) for k, v in incoming.items()}
        return {
            "X-Internal-Token": lower.get("x-internal-token", os.getenv("AGENT_INTERNAL_TOKEN", "")),
            "X-User-Id": lower.get("x-user-id", ""),
            "X-Request-Id": lower.get("x-request-id", ""),
        }

    def _handle_response(self, response: httpx.Response) -> dict:
        try:
            data = response.json()
        except ValueError:
            data = None

        if response.status_code == 200:
            return data if isinstance(data, dict) else {"code": 0, "data": data}

        message = ""
        if isinstance(data, dict):
            message = str(data.get("message") or "")
        if not message:
            message = f"HTTP {response.status_code}"
        return {
            "code": response.status_code,
            "message": message,
            "data": data,
            "errorType": _ERROR_TYPES.get(response.status_code, "http_error"),
            "retryable": response.status_code in _RETRYABLE,
        }

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()


erp_client = ERPHttpClient()
