"""审批待办、时间线与经营概览 MCP 工具（只读）。"""
import json

from fastmcp import FastMCP

from src.mcp_server.http_base import erp_client


def register_workflow_tools(mcp: FastMCP):
    """注册审批与经营概览工具到 MCP Server"""

    @mcp.tool()
    async def workflow_todo() -> str:
        """查询当前用户的待审批任务（按登录身份数据范围过滤）。

        Returns:
            待办列表JSON，包含业务类型、单号、标题、金额、创建时间等
        """
        result = await erp_client.get("/api/workflow/todo")
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def workflow_done() -> str:
        """查询当前用户已处理的审批任务。

        Returns:
            已办列表JSON
        """
        result = await erp_client.get("/api/workflow/done")
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def workflow_timeline(business_type: str, business_id: int) -> str:
        """查询单据的审批流转记录。

        Args:
            business_type: 业务类型，如 PURCHASE_REQUISITION / PURCHASE_ORDER
            business_id: 业务单据ID

        Returns:
            审批时间线JSON
        """
        result = await erp_client.get(
            f"/api/workflow/timeline/{business_type}/{business_id}"
        )
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def dashboard_summary() -> str:
        """获取经营看板概览：待审批、采购金额、执行中订单、低库存、趋势与供应商排名。

        Returns:
            看板数据JSON
        """
        result = await erp_client.get("/api/dashboard/summary")
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def alerts_summary(
        qualification_days: int = 30,
        delivery_days: int = 7,
        approval_hours: int = 24,
    ) -> str:
        """获取风险提醒：供应商资质临期、交付临期、审批积压。

        Args:
            qualification_days: 资质到期预警天数，默认30
            delivery_days: 交付日期预警天数，默认7
            approval_hours: 审批积压小时数，默认24

        Returns:
            三类提醒JSON
        """
        params = {
            "qualificationDays": qualification_days,
            "deliveryDays": delivery_days,
            "approvalHours": approval_hours,
        }
        result = await erp_client.get("/api/alerts/summary", params=params)
        return json.dumps(result, ensure_ascii=False, indent=2)
