"""
全局配置模块
LLM、Store、Checkpointer、沙箱连接参数
"""
import os
from langchain_deepseek import ChatDeepSeek
from .env_utils import get_env, get_env_int

# ============ LLM 配置 ============
LLM_MODEL = get_env("LLM_MODEL", "deepseek-flash")
LLM_BASE_URL = get_env("LLM_BASE_URL", "https://api.deepseek.com")
LLM_API_KEY = get_env("DEEPSEEK_API_KEY", "")
LLM_TEMPERATURE = 0.1
LLM_MAX_TOKENS = get_env_int("LLM_MAX_TOKENS", 4096)
LLM_REASONING_EFFORT = get_env("LLM_REASONING_EFFORT", "high")
# 思考模式：带工具调用时，若 SDK 未回传 reasoning_content，DeepSeek 会返回 400；
# 因此默认关闭，分析/报告类调用可单独传 thinking=True。
LLM_THINKING = get_env("LLM_THINKING", "false").strip().lower() in {"1", "true", "yes", "on"}
# 可选的请求追踪头：两个都配置后才生效（具体 header 名由调用方确认）。
DEEPSEEK_TRACKING_ID = get_env("DEEPSEEK_TRACKING_ID", "")
DEEPSEEK_TRACKING_HEADER = get_env("DEEPSEEK_TRACKING_HEADER", "")


def get_llm(*, thinking: bool | None = None, timeout: float | None = None,
            max_retries: int = 2, max_tokens: int = LLM_MAX_TOKENS) -> ChatDeepSeek:
    """获取 DeepSeek 模型实例。

    主 Agent 使用思考模式；需要强制结构化输出的内部评审器使用
    非思考模式，避免 DeepSeek 拒绝 ``tool_choice`` 参数。
    ``thinking=None`` 时读取 ``LLM_THINKING``（默认关闭）。
    """
    if thinking is None:
        thinking = LLM_THINKING

    common_kwargs = {
        "model": LLM_MODEL,
        "base_url": LLM_BASE_URL,
        "api_key": LLM_API_KEY,
        "max_tokens": max_tokens,
        "max_retries": max_retries,
    }
    if DEEPSEEK_TRACKING_ID and DEEPSEEK_TRACKING_HEADER:
        common_kwargs["default_headers"] = {
            DEEPSEEK_TRACKING_HEADER: DEEPSEEK_TRACKING_ID,
        }
    if timeout is not None:
        common_kwargs["timeout"] = timeout
    if thinking:
        return ChatDeepSeek(
            **common_kwargs,
            reasoning_effort=LLM_REASONING_EFFORT,
            extra_body={"thinking": {"type": "enabled"}},
        )
    return ChatDeepSeek(
        **common_kwargs,
        temperature=LLM_TEMPERATURE,
        extra_body={"thinking": {"type": "disabled"}},
    )


# ============ MongoDB 配置 ============
MONGODB_URI = get_env("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB_NAME = get_env("MONGODB_DB_NAME", "erp_agent")

# ============ MCP Server 配置 ============
MCP_SERVER_URL = get_env("MCP_SERVER_URL", "http://localhost:9000")
MCP_SSE_URL = f"{MCP_SERVER_URL}/sse"

# ============ 沙箱配置 ============
SANDBOX_IMAGE = get_env("SANDBOX_IMAGE", "python:3.11-slim")#Docker 镜像名称，具体是 Python 3.11 的 slim（精简）版本
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
INTERRUPT_ON_TOOLS = {
    "order_create": {"allowed_decisions": ["approve", "reject"]},
    "order_update": {"allowed_decisions": ["approve", "reject"]},
    "order_cancel": {"allowed_decisions": ["approve", "reject"]},
    "requisition_create": {"allowed_decisions": ["approve", "reject"]},
    "requisition_submit": {"allowed_decisions": ["approve", "reject"]},
    "requisition_cancel": {"allowed_decisions": ["approve", "reject"]},
    "requisition_convert": {"allowed_decisions": ["approve", "reject"]},
}
