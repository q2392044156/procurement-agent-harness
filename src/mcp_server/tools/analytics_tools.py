"""经营分析 MCP 工具：记分卡、库存风险、花费分析、审批 SLA、价格趋势。"""
import json
from datetime import datetime, timezone

from fastmcp import FastMCP

from ..http_base import erp_client


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def register_analytics_tools(mcp: FastMCP):
    """注册分析工具到 MCP Server"""

    @mcp.tool()
    async def supplier_scorecard(supplier_id: int, year: int = 0) -> str:
        """供应商记分卡：年度采购额、订单数、评分、资质最近到期日、平均交付天数、取消次数。

        Args:
            supplier_id: 供应商ID
            year: 财年，0 表示当前年度

        Returns:
            记分卡JSON（金额保留两位小数）
        """
        result = await erp_client.get(
            f"/api/analytics/suppliers/{supplier_id}/scorecard", params={"year": year}
        )
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def inventory_risk() -> str:
        """库存风险清单：低于安全库存的物资，含缺口、在途数量与净缺口。

        Returns:
            风险列表JSON，riskLevel 为 HIGH / COVERED / LOW
        """
        result = await erp_client.get("/api/analytics/inventory-risk")
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def spend_analysis(year: int = 0, group_by: str = "department") -> str:
        """采购花费分析：按部门/供应商/分类/月份汇总金额与订单数。

        Args:
            year: 财年，0 表示当前年度
            group_by: 统计维度，department / supplier / category / month

        Returns:
            汇总JSON，含 total 与 records
        """
        result = await erp_client.get(
            "/api/analytics/spend", params={"year": year, "groupBy": group_by}
        )
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def approval_sla(threshold_hours: int = 24) -> str:
        """审批 SLA：统计当前用户待办任务的等待时长与超时数量。

        Args:
            threshold_hours: 超时阈值（小时），默认24

        Returns:
            JSON，含 total、overdue、averageHours 与明细
        """
        response = await erp_client.get("/api/workflow/todo")
        items = response.get("data") if isinstance(response, dict) else []
        now = datetime.now(timezone.utc)
        rows = []
        total_hours = 0.0
        overdue = 0
        for item in items or []:
            created = _parse_dt(item.get("createdAt"))
            hours = round((now - created).total_seconds() / 3600, 1) if created else None
            if hours is not None:
                total_hours += hours
                if hours > threshold_hours:
                    overdue += 1
            rows.append(
                {
                    "taskId": item.get("id"),
                    "name": item.get("name"),
                    "businessKey": item.get("businessKey"),
                    "createdAt": item.get("createdAt"),
                    "hoursPending": hours,
                    "overdue": bool(hours is not None and hours > threshold_hours),
                }
            )
        payload = {
            "code": 0,
            "data": {
                "thresholdHours": threshold_hours,
                "total": len(rows),
                "overdue": overdue,
                "averageHours": round(total_hours / len(rows), 1) if rows else 0,
                "tasks": rows,
            },
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def price_trend(material_id: int, months: int = 12) -> str:
        """物资历史成交价趋势：样本数、最新价、均价、最低/最高价与涨跌幅。

        Args:
            material_id: 物资ID
            months: 观察窗口（月），默认12

        Returns:
            趋势JSON（按当前用户数据范围）
        """
        response = await erp_client.get(f"/api/parts/{material_id}/price-history")
        rows = response.get("data") if isinstance(response, dict) else []
        rows = rows or []
        prices = [float(row["unitPrice"]) for row in rows if row.get("unitPrice") is not None]
        payload = {
            "materialId": material_id,
            "months": months,
            "sampleCount": len(prices),
            "latestPrice": prices[0] if prices else None,
            "earliestPrice": prices[-1] if prices else None,
            "averagePrice": round(sum(prices) / len(prices), 2) if prices else None,
            "minPrice": min(prices) if prices else None,
            "maxPrice": max(prices) if prices else None,
            "changePercent": (
                round((prices[0] - prices[-1]) / prices[-1] * 100, 1)
                if len(prices) >= 2 and prices[-1]
                else None
            ),
        }
        return json.dumps({"code": 0, "data": payload}, ensure_ascii=False, indent=2)
