"""
LLM 工厂：DeepSeek 模型配置与实例化。

只负责「模型怎么造」，不负责业务运行的其它配置（库、端口、沙箱等见 settings.py）。
思考模式默认关闭：带工具调用时若 SDK 未回传 reasoning_content，DeepSeek 会返回 400；
分析/报告类调用可单独传 ``thinking=True``。
"""
from langchain_deepseek import ChatDeepSeek

from src.core.env import get_env, get_env_int

# ============ LLM 配置 ============
LLM_MODEL = get_env("LLM_MODEL", "deepseek-flash")
LLM_BASE_URL = get_env("LLM_BASE_URL", "https://api.deepseek.com")
LLM_API_KEY = get_env("DEEPSEEK_API_KEY", "")
LLM_TEMPERATURE = 0.1
LLM_MAX_TOKENS = get_env_int("LLM_MAX_TOKENS", 4096)
LLM_REASONING_EFFORT = get_env("LLM_REASONING_EFFORT", "high")
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
