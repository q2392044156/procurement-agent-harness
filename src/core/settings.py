"""
运行配置模块：MongoDB、MCP Server、沙箱、Store 命名空间、限流与中断策略。

模型相关配置在 core/llm.py（get_llm / LLM_*），路径在 core/paths.py。
"""
from src.core.env import get_env, get_env_int

# ============ MongoDB 配置 ============
MONGODB_URI = get_env("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB_NAME = get_env("MONGODB_DB_NAME", "erp_agent")

# ============ MCP Server 配置 ============
MCP_SERVER_URL = get_env("MCP_SERVER_URL", "http://localhost:9000")
MCP_SSE_URL = f"{MCP_SERVER_URL}/sse"

# ============ 沙箱配置 ============
SANDBOX_IMAGE = get_env("SANDBOX_IMAGE", "python:3.11-slim")  # Docker 镜像名称，具体是 Python 3.11 的 slim（精简）版本
SANDBOX_WORK_DIR = "/workspace"
SANDBOX_SKILLS_DIR = "/skills"
SANDBOX_MEMORIES_DIR = "/memories"
SANDBOX_WARM_POOL_SIZE = get_env_int("SANDBOX_WARM_POOL_SIZE", 1)
SANDBOX_IDLE_TIMEOUT_MINUTES = get_env_int("SANDBOX_IDLE_TIMEOUT_MINUTES", 30)
SANDBOX_MAINTENANCE_INTERVAL_SECONDS = get_env_int(
    "SANDBOX_MAINTENANCE_INTERVAL_SECONDS", 60
)
SANDBOX_HEALTH_CHECK_INTERVAL_SECONDS = get_env_int(
    "SANDBOX_HEALTH_CHECK_INTERVAL_SECONDS", 30
)

# ============ Store 命名空间 ============
SKILLS_STORE_NAMESPACE = ("persisted-skills",)
PREFERENCES_STORE_NAMESPACE = ("user-preferences",)


def skills_store_namespace(user_id: str) -> tuple[str, str]:
    """Return the isolated Store namespace for one user's custom Skills."""
    return (*SKILLS_STORE_NAMESPACE, user_id)

# ============ Agent 配置 ============
MAX_MODEL_CALLS = get_env_int("MAX_MODEL_CALLS", 50)
MAX_TOOL_CALLS = get_env_int("MAX_TOOL_CALLS", 30)
SUMMARIZATION_THRESHOLD = 0.85  # 85% 上下文窗口时触发摘要

# ============ 中断配置 ============
# 所有写操作都必须人工确认；只读工具不中断。
# 值必须是 True（或 HumanInTheLoopMiddleware 的 InterruptOnConfig），
# 传 dict 会被 deepagents 静默忽略，导致写操作直接执行。
_WRITE_TOOLS = (
    "order_create",
    "order_update",
    "order_submit",
    "order_close",
    "order_cancel",
    "requisition_create",
    "requisition_submit",
    "requisition_cancel",
    "requisition_convert",
)
INTERRUPT_ON_TOOLS = {name: True for name in _WRITE_TOOLS}
