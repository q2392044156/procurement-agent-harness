"""采购申请与审批相关 MCP 工具。"""
import json

from fastmcp import FastMCP

from src.mcp_server.http_base import erp_client
from src.mcp_server.tools._result import check_batch, idempotency_headers, mark_verified


def register_requisition_tools(mcp: FastMCP):
    """注册采购申请工具到 MCP Server"""

    @mcp.tool()
    async def requisition_page(
        current: int = 1,
        size: int = 10,
        keyword: str = None,
        status: str = None,
    ) -> str:
        """分页查询采购申请。

        Args:
            current: 当前页码，默认1
            size: 每页大小，默认10
            keyword: 申请单号或用途关键字（可选）
            status: 申请状态（可选），如 DRAFT/PENDING_APPROVAL/APPROVED/REJECTED/CONVERTED

        Returns:
            分页数据JSON，包含 records、total、current、size、pages
        """
        params = {"current": current, "size": size, "keyword": keyword, "status": status}
        result = await erp_client.get("/api/requisitions/page", params=params)
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def requisition_get(id: int) -> str:
        """获取采购申请详情，包含明细、审批状态与流程实例。

        Args:
            id: 采购申请ID

        Returns:
            申请详情JSON
        """
        result = await erp_client.get(f"/api/requisitions/get/{id}")
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def requisition_create(
        required_date: str,
        purpose: str,
        items: list[dict],
        idempotency_key: str = None,
    ) -> str:
        """创建采购申请草稿（需人工确认）。

        Args:
            required_date: 期望到货日期，格式 YYYY-MM-DD
            purpose: 申请用途
            items: 明细数组，元素字段：materialId、quantity、estimatedUnitPrice、remark（可选）
            idempotency_key: 幂等键（可选；重试时传同一个值）

        Returns:
            创建后的申请详情JSON（含 id、requisitionNo、verified=true）
        """
        check_batch(items)
        payload = {"requiredDate": required_date, "purpose": purpose, "items": items}
        result = await erp_client.post(
            "/api/requisitions", json_data=payload,
            headers=idempotency_headers(idempotency_key),
        )
        return json.dumps(mark_verified(result), ensure_ascii=False, indent=2)

    @mcp.tool()
    async def requisition_submit(id: int, idempotency_key: str = None) -> str:
        """提交采购申请进入审批（需人工确认）。

        Args:
            id: 采购申请ID
            idempotency_key: 幂等键（可选）

        Returns:
            提交后的申请详情JSON（status 进入待审批，verified=true）
        """
        result = await erp_client.post(
            f"/api/requisitions/{id}/submit",
            headers=idempotency_headers(idempotency_key),
        )
        return json.dumps(mark_verified(result), ensure_ascii=False, indent=2)

    @mcp.tool()
    async def requisition_cancel(id: int, reason: str, idempotency_key: str = None) -> str:
        """取消采购申请（需人工确认）。

        Args:
            id: 采购申请ID
            reason: 取消原因
            idempotency_key: 幂等键（可选）

        Returns:
            取消后的申请详情JSON
        """
        result = await erp_client.post(
            f"/api/requisitions/{id}/cancel",
            json_data={"reason": reason},
            headers=idempotency_headers(idempotency_key),
        )
        return json.dumps(mark_verified(result), ensure_ascii=False, indent=2)

    @mcp.tool()
    async def requisition_convert(
        id: int,
        supplier_id: int,
        delivery_date: str,
        tax_rate: float = 0.13,
        terms: str = None,
        price_overrides: dict = None,
        idempotency_key: str = None,
    ) -> str:
        """把已批准的采购申请转为采购订单（需人工确认）。

        Args:
            id: 采购申请ID（必须已批准）
            supplier_id: 供应商ID（必须为合格状态）
            delivery_date: 交付日期 YYYY-MM-DD
            tax_rate: 税率，默认 0.13
            terms: 付款/交付条款（可选）
            price_overrides: 价格覆盖对象，{"物资ID": 单价}（可选）
            idempotency_key: 幂等键（可选）

        Returns:
            新建订单详情JSON（verified=true）
        """
        payload = {
            "supplierId": supplier_id,
            "deliveryDate": delivery_date,
            "taxRate": tax_rate,
            "terms": terms,
        }
        if price_overrides:
            payload["priceOverrides"] = price_overrides
        result = await erp_client.post(
            f"/api/requisitions/{id}/convert", json_data=payload,
            headers=idempotency_headers(idempotency_key),
        )
        return json.dumps(mark_verified(result), ensure_ascii=False, indent=2)
