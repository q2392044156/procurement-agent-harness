"""收货单 MCP 工具（只读）。"""
import json

from fastmcp import FastMCP

from ..http_base import erp_client


def register_receipt_tools(mcp: FastMCP):
    """注册收货工具到 MCP Server"""

    @mcp.tool()
    async def receipt_page(
        current: int = 1,
        size: int = 10,
        order_no: str = None,
    ) -> str:
        """分页查询收货记录。

        Args:
            current: 当前页码，默认1
            size: 每页大小，默认10
            order_no: 采购订单号（可选）

        Returns:
            分页收货记录JSON
        """
        params = {"current": current, "size": size, "orderNo": order_no}
        result = await erp_client.get("/api/receipts/page", params=params)
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def receipt_get(id: int) -> str:
        """获取收货单详情，包含批次/序列号与收货明细。

        Args:
            id: 收货单ID

        Returns:
            收货单详情JSON
        """
        result = await erp_client.get(f"/api/receipts/get/{id}")
        return json.dumps(result, ensure_ascii=False, indent=2)
