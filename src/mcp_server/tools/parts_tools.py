"""
产品/零部件管理 MCP 工具
part_query / part_search / part_by_supplier / part_page
"""
import json
from fastmcp import FastMCP
from src.mcp_server.http_base import erp_client


def register_parts_tools(mcp: FastMCP):
    """注册零部件管理工具到 MCP Server"""

    @mcp.tool()
    async def part_query(id: int) -> str:
        """获取单个零部件的详细信息。

        Args:
            id: 零部件ID

        Returns:
            零部件详细信息JSON，包含 partCode, name, model, specification, unit, purchasePrice, suggestedRetailPrice, stockWarningValue, supplierId, category, description
        """
        result = await erp_client.get(f"/api/parts/get/{id}")
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def part_search(
        q: str = None,
        name: str = None,
        brand: str = None,
        category: str = None,
        specification: str = None,
        tracking_mode: str = None,
    ) -> str:
        """按关键字模糊搜索物资，支持编码/名称/品牌/规格/分类。

        Args:
            q: 统一模糊关键字，例如"联想"、"车间"、"6308"、"NSK"
            name: 名称关键字（兼容旧参数，q 为空时使用）
            brand: 品牌过滤，例如"联想"、"NSK"、"西门子"
            category: 分类过滤，例如"电脑配件"、"轴承"、"劳保"
            specification: 规格关键字，例如"6308"、"IP65"、"380V"
            tracking_mode: 追踪方式：SERIAL / BATCH / QUANTITY

        Returns:
            匹配的物资列表 JSON（含 partCode、name、brand、specification、category）
        """
        params = {
            "q": q,
            "name": name,
            "brand": brand,
            "category": category,
            "specification": specification,
            "trackingMode": tracking_mode,
        }
        result = await erp_client.get("/api/parts/search", params=params)
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def part_by_supplier(supplier_id: int) -> str:
        """获取指定供应商的所有产品列表。

        Args:
            supplier_id: 供应商ID

        Returns:
            该供应商提供的零部件列表JSON
        """
        result = await erp_client.get(f"/api/parts/supplier/{supplier_id}")
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def part_page(
        current: int = 1,
        size: int = 10,
        name: str = None,
        q: str = None,
        brand: str = None,
        category: str = None,
        specification: str = None,
        tracking_mode: str = None,
        supplier_id: int = None,
    ) -> str:
        """分页查询物资，支持编码/名称/品牌/规格/分类模糊过滤。

        Args:
            current: 当前页码，默认1
            size: 每页大小，默认10
            name: 名称关键字（兼容旧参数）
            q: 统一模糊关键字（编码/名称/品牌/规格/分类）
            brand: 品牌过滤
            category: 分类过滤
            specification: 规格过滤
            tracking_mode: SERIAL / BATCH / QUANTITY
            supplier_id: 供应商ID（可选）

        Returns:
            分页物资数据JSON，包含 records, total, current, size, pages
        """
        params = {
            "current": current,
            "size": size,
            "name": name,
            "q": q,
            "brand": brand,
            "category": category,
            "specification": specification,
            "trackingMode": tracking_mode,
            "supplierId": supplier_id,
        }
        result = await erp_client.get("/api/parts/page", params=params)
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def part_create(
        part_code: str,
        name: str,
        purchase_price: float,
        model: str = None,
        specification: str = None,
        unit: str = None,
        suggested_retail_price: float = None,
        stock_warning_value: int = None,
        supplier_id: int = None,
        category: str = None,
        description: str = None,
    ) -> str:
        """创建新零部件。

        Args:
            part_code: 零件编码（必填）
            name: 零件名称（必填）
            purchase_price: 采购单价（必填，>=0）
            model: 型号
            specification: 规格
            unit: 单位（个/套/件）
            suggested_retail_price: 建议零售价
            stock_warning_value: 库存预警值
            supplier_id: 供应商ID
            category: 分类
            description: 描述

        Returns:
            创建结果JSON
        """
        data = {
            "partCode": part_code,
            "name": name,
            "purchasePrice": purchase_price,
            "model": model,
            "specification": specification,
            "unit": unit,
            "suggestedRetailPrice": suggested_retail_price,
            "stockWarningValue": stock_warning_value,
            "supplierId": supplier_id,
            "category": category,
            "description": description,
        }
        data = {k: v for k, v in data.items() if v is not None}
        result = await erp_client.post("/api/parts/create", json_data=data)
        return json.dumps(result, ensure_ascii=False, indent=2)
