"""仓库、出库、预算、合同与历史成交价 MCP 工具（只读）。"""
import json

from fastmcp import FastMCP

from src.mcp_server.http_base import erp_client


def register_operations_tools(mcp: FastMCP):
    """注册运营类只读工具到 MCP Server"""

    @mcp.tool()
    async def warehouse_list() -> str:
        """列出所有仓库，包含余额条数与收货条数。

        Returns:
            仓库列表JSON（id、code、name、address、manager、enabled）
        """
        result = await erp_client.get("/api/warehouses")
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def warehouse_get(id: int) -> str:
        """获取单个仓库详情。

        Args:
            id: 仓库ID

        Returns:
            仓库详情JSON
        """
        result = await erp_client.get(f"/api/warehouses/{id}")
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def issue_page(
        current: int = 1,
        size: int = 10,
        keyword: str = None,
    ) -> str:
        """分页查询出库/领用记录。

        Args:
            current: 当前页码，默认1
            size: 每页大小，默认10
            keyword: 出库单号、物资编码或名称（可选）

        Returns:
            分页出库记录JSON
        """
        params = {"current": current, "size": size, "keyword": keyword}
        result = await erp_client.get("/api/inventory/issues", params=params)
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def issue_get(id: int) -> str:
        """获取出库/领用详情。

        Args:
            id: 出库记录ID

        Returns:
            出库详情JSON
        """
        result = await erp_client.get(f"/api/inventory/issues/{id}")
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def budget_list(year: int = 0) -> str:
        """查询部门年度预算，包含已占用、可用额度与使用率。

        Args:
            year: 财年，0 表示当前年度

        Returns:
            预算列表JSON
        """
        result = await erp_client.get("/api/budgets", params={"year": year})
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def contract_page(
        current: int = 1,
        size: int = 10,
        keyword: str = None,
        status: str = None,
    ) -> str:
        """分页查询合同台账。

        Args:
            current: 当前页码，默认1
            size: 每页大小，默认10
            keyword: 合同号、名称或供应商（可选）
            status: 合同状态（可选），如 DRAFT/ACTIVE/EXPIRED/TERMINATED

        Returns:
            分页合同JSON
        """
        params = {
            "current": current,
            "size": size,
            "keyword": keyword,
            "status": status,
        }
        result = await erp_client.get("/api/contracts/page", params=params)
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def contract_get(id: int) -> str:
        """获取合同详情。

        Args:
            id: 合同ID

        Returns:
            合同详情JSON
        """
        result = await erp_client.get(f"/api/contracts/get/{id}")
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def part_price_history(id: int) -> str:
        """查询物资的历史成交价（最近 50 条订单明细，按当前用户数据范围）。

        Args:
            id: 物资ID

        Returns:
            历史价格JSON（订单号、供应商、单价、数量、下单时间）
        """
        result = await erp_client.get(f"/api/parts/{id}/price-history")
        return json.dumps(result, ensure_ascii=False, indent=2)
