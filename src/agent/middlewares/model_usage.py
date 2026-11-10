"""模型调用用量记录：输入/输出 token、模型名、线程与用户。

DeepSeek 流式响应不返回 usage，因此采用 tiktoken/字符数估算，
并在记录中标记 ``estimated=true``。
"""
import json
import os
import time
from pathlib import Path

from langchain.agents.middleware import AgentMiddleware

from ..observability import current_trace

ROOT = Path(__file__).resolve().parents[3]
USAGE_FILE = Path(os.getenv("MODEL_USAGE_FILE", str(ROOT / "logs" / "model_usage.jsonl")))

try:
    import tiktoken

    _ENCODER = tiktoken.get_encoding("cl100k_base")
except Exception:  # noqa: BLE001
    _ENCODER = None


def _count(text: str) -> int:
    if not text:
        return 0
    if _ENCODER is not None:
        try:
            return len(_ENCODER.encode(text))
        except Exception:  # noqa: BLE001
            pass
    return max(1, len(text) // 2)


def _thread_id() -> str | None:
    try:
        from langgraph.config import get_config

        return get_config().get("configurable", {}).get("thread_id")
    except Exception:
        return None


class ModelUsageMiddleware(AgentMiddleware):
    """记录每次模型调用的 token 用量（流式场景为估算值）。"""

    def __init__(self, user_id: str | None = None):
        super().__init__()
        self.user_id = user_id

    async def awrap_model_call(self, request, handler):
        started = time.perf_counter()
        response = await handler(request)
        usage = getattr(response, "usage_metadata", None) or {}
        metadata = getattr(response, "response_metadata", None) or {}
        token_usage = metadata.get("token_usage") or {}
        input_tokens = usage.get("input_tokens") or token_usage.get("prompt_tokens")
        output_tokens = usage.get("output_tokens") or token_usage.get("completion_tokens")
        estimated = False
        if not input_tokens:
            texts = [str(getattr(message, "content", "")) for message in getattr(request, "messages", [])]
            input_tokens = sum(_count(text) for text in texts) + 4 * len(texts)
            estimated = True
        if not output_tokens:
            output_tokens = _count(str(getattr(response, "content", "") or ""))
            estimated = True
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "trace_id": current_trace().trace_id if current_trace() else None,
            "thread_id": _thread_id(),
            "user_id": self.user_id,
            "model": metadata.get("model_name") or metadata.get("model") or "deepseek",
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
            "estimated": estimated,
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        }
        trace = current_trace()
        if trace is not None:
            trace.add_model(record["model"], record["input_tokens"], record["output_tokens"],
                            record["duration_ms"], estimated)
        try:
            USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with USAGE_FILE.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass
        return response
