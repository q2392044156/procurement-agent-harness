"""
采购订单管理 MCP 工具
order_create / order_update / order_page / order_get / order_search_details / order_statistics
"""
import json
from typing import Optional
from fastmcp import FastMCP
from src.mcp_server.http_base import erp_client
from src.mcp_server.tools._result import check_batch, idempotency_headers, mark_verified


def register_order_tools(mcp: FastMCP):
    """注册采购订单管理工具到 MCP Server"""

    @mcp.tool()
    async def order_create(order_data: str, idempotency_key: str = None) -> str:
        """创建直采采购订单（需人工确认）。

        Args:
            order_data: 订单 JSON 字符串，字段与平台契约一致：
                {
                    "supplierId": 1,                 // 必填，合格供应商ID
                    "deliveryDate": "2026-11-20",    // 必填，交付日期 YYYY-MM-DD
                    "taxRate": 0.13,                 // 税率 0~1
                    "terms": "月结30天",              // 可选
                    "orderDetail": [                 // 必填，至少一条
                        {"partId": 1, "quantity": 10, "unitPrice": 25.5, "remark": "可选"}
                    ]
                }

        Returns:
            创建后的订单详情 JSON（含 id、orderNo、status、items）
        """
        try:
            data = json.loads(order_data) if isinstance(order_data, str) else order_data
        except json.JSONDecodeError as e:
            return json.dumps({"code": 400, "message": f"JSON解析失败: {e}", "data": None,
                               "errorType": "validation", "retryable": False}, ensure_ascii=False)
        if not isinstance(data, dict) or "supplierId" not in data or "orderDetail" not in data:
            return json.dumps({"code": 400, "message": "缺少 supplierId 或 orderDetail",
                               "errorType": "validation", "retryable": False}, ensure_ascii=False)
        try:
            check_batch(data["orderDetail"])
        except ValueError as e:
            return json.dumps({"code": 400, "message": str(e),
                               "errorType": "validation", "retryable": False}, ensure_ascii=False)
        result = await erp_client.post(
            "/api/orders/create", json_data=data,
            headers=idempotency_headers(idempotency_key),
        )
        return json.dumps(mark_verified(result), ensure_ascii=False, indent=2)

    @mcp.tool()
    async def order_update(id: int, order_data: str, idempotency_key: str = None) -> str:
        """修改草稿/驳回状态的订单（需人工确认）。

        Args:
            id: 订单ID
            order_data: 字段同 order_create；其中 orderDetail 必须提交全部明细：
                {"supplierId": 1, "deliveryDate": "2026-11-20", "taxRate": 0.13,
                 "terms": "月结30天",
                 "items": [{"id": 5, "unitPrice": 25.5, "remark": "可选"}]}

        Returns:
            修改后的订单详情 JSON
        """
        try:
            data = json.loads(order_data) if isinstance(order_data, str) else order_data
        except json.JSONDecodeError as e:
            return json.dumps({"code": 400, "message": f"JSON解析失败: {e}", "data": None}, ensure_ascii=False)
        result = await erp_client.put(
            f"/api/orders/update/{id}", json_data=data,
            headers=idempotency_headers(idempotency_key),
        )
        return json.dumps(mark_verified(result), ensure_ascii=False, indent=2)

    @mcp.tool()
    async def order_page(
        current: int = 1,
        size: int = 10,
        order_number: str = None,
        status: str = None,
        start_date: str = None,
        end_date: str = None,
    ) -> str:
        """分页查询采购订单列表。

        Args:
            current: 当前页码，默认1
            size: 每页大小，默认10
            order_number: 订单号（可选，模糊匹配）
            status: 订单状态（可选）：DRAFT/PENDING_APPROVAL/APPROVED/PARTIALLY_RECEIVED/
                RECEIVED/CANCELLED/CLOSED
            start_date: 开始日期（可选），格式 yyyy-MM-dd
            end_date: 结束日期（可选），格式 yyyy-MM-dd

        Returns:
            分页订单数据JSON
        """
        params = {
            "current": current,
            "size": size,
            "orderNumber": order_number,
            "status": status,
            "startDate": start_date,
            "endDate": end_date,
        }
        result = await erp_client.get("/api/orders/page", params=params)
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def order_get(id: int) -> str:
        """获取单个采购订单的详细信息（含订单明细）。

        Args:
            id: 订单ID

        Returns:
            订单详细信息JSON，包含 orderNumber, totalAmount, status, orderTime, orderDetail[]
        """
        result = await erp_client.get(f"/api/orders/get/{id}")
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def order_search_details(
        part_name: str = None,
        start_date: str = None,
        end_date: str = None,
    ) -> str:
        """搜索订单明细，支持按零部件名称和时间范围过滤。

        Args:
            part_name: 零部件名称（可选，模糊匹配）
            start_date: 开始时间（可选），支持 yyyy-MM-dd 或 yyyy-MM-dd HH:mm:ss
            end_date: 结束时间（可选），支持 yyyy-MM-dd 或 yyyy-MM-dd HH:mm:ss

        Returns:
            订单明细列表JSON，每条包含零部件信息和供应商信息
        """
        params = {
            "partName": part_name,
            "startDate": start_date,
            "endDate": end_date,
        }
        result = await erp_client.get("/api/orders/search-details", params=params)
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def order_statistics(
        start_date: str = None,
        end_date: str = None,
    ) -> str:
        """获取采购统计数据。

        Args:
            start_date: 开始日期（可选），格式 yyyy-MM-dd
            end_date: 结束日期（可选），格式 yyyy-MM-dd

        Returns:
            采购统计JSON，包含订单总数、总金额、各状态数量等
        """
        params = {
            "startDate": start_date,
            "endDate": end_date,
        }
        result = await erp_client.get("/api/orders/statistics", params=params)
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def order_submit(id: int, idempotency_key: str = None) -> str:
        """提交订单进入审批（需人工确认）。仅草稿/驳回状态可提交。

        Args:
            id: 订单ID
            idempotency_key: 幂等键（可选）

        Returns:
            操作结果 JSON
        """
        result = await erp_client.patch(
            f"/api/orders/update-status/{id}", params={"status": "1"},
            headers=idempotency_headers(idempotency_key),
        )
        return json.dumps(mark_verified(result), ensure_ascii=False, indent=2)

    @mcp.tool()
    async def order_close(id: int, idempotency_key: str = None) -> str:
        """关闭已完成收货的订单。

        Args:
            id: 订单ID
            idempotency_key: 幂等键（可选）

        Returns:
            操作结果 JSON
        """
        result = await erp_client.patch(
            f"/api/orders/update-status/{id}", params={"status": "4"},
            headers=idempotency_headers(idempotency_key),
        )
        return json.dumps(mark_verified(result), ensure_ascii=False, indent=2)

    @mcp.tool()
    async def order_cancel(id: int, reason: str, idempotency_key: str = None) -> str:
        """取消采购订单（需人工确认；草稿/驳回/待审批/已批准且未收货可取消）。

        Args:
            id: 订单ID
            reason: 取消原因（必填）
            idempotency_key: 幂等键（可选）

        Returns:
            取消后的订单详情JSON（status=CANCELLED）
        """
        result = await erp_client.post(
            f"/api/orders/{id}/cancel", json_data={"reason": reason},
            headers=idempotency_headers(idempotency_key),
        )
        return json.dumps(mark_verified(result), ensure_ascii=False, indent=2)
