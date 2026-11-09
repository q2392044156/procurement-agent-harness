"""采购申请与审批相关 MCP 工具（只读）。"""
import json

from fastmcp import FastMCP

from ..http_base import erp_client


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
            status: 申请状态（可选），如 DRAFT/PENDING_DEPARTMENT/PENDING_PURCHASER/
                PENDING_FINANCE/PENDING_GENERAL_MANAGER/APPROVED/REJECTED/CONVERTED

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
