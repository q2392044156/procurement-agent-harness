"""
MCP Server 入口
FastMCP 实例创建，注册所有 tools，SSE 传输协议
"""
import sys
import os
import threading

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from fastmcp import FastMCP
from src.mcp_server.server_config import MCP_HOST, MCP_PORT
from src.mcp_server.tools.suppliers_tools import register_supplier_tools
from src.mcp_server.tools.parts_tools import register_parts_tools
from src.mcp_server.tools.order_tools import register_order_tools
from src.mcp_server.tools.inventory_tools import register_inventory_tools
from src.mcp_server.tools.requisition_tools import register_requisition_tools
from src.mcp_server.tools.workflow_tools import register_workflow_tools
from src.mcp_server.tools.receipt_tools import register_receipt_tools
from src.mcp_server.tools.operations_tools import register_operations_tools
from src.mcp_server.tools.analytics_tools import register_analytics_tools
from src.kb.tools import register_kb_tools

# 创建 MCP Server 实例
mcp = FastMCP(
    name="ERP-Procurement-MCP",
    instructions="制造企业智能采购与物资供应链平台 MCP 网关，提供供应商、物资、采购订单与库存查询和管理能力。",
)

# 注册所有工具
register_supplier_tools(mcp)
register_parts_tools(mcp)
register_order_tools(mcp)
register_inventory_tools(mcp)
register_requisition_tools(mcp)
register_workflow_tools(mcp)
register_receipt_tools(mcp)
register_operations_tools(mcp)
register_analytics_tools(mcp)
register_kb_tools(mcp)


def _warmup_kb() -> None:
    """后台预热：加载 bge-m3 并确保 Qdrant 集合存在，降低首次检索延迟。"""
    try:
        from src.kb.embedder import dimension
        from src.kb.store import ensure_collection

        ensure_collection(dimension())
        print("[MCP] KB warmup finished (bge-m3 loaded, collection ready)")
    except Exception as exc:  # noqa: BLE001
        print(f"[MCP] KB warmup skipped: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    print(f"[MCP] Starting on {MCP_HOST}:{MCP_PORT} (SSE transport)")
    threading.Thread(target=_warmup_kb, name="kb-warmup", daemon=True).start()
    mcp.run(transport="sse", host=MCP_HOST, port=MCP_PORT)
