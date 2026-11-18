"""精排：优先 fastembed ONNX cross-encoder，失败时回退到 LLM 打分。"""
from __future__ import annotations

import json
import re

from src.kb.config import FASTEMBED_CACHE, RERANK_MODEL, RERANKER

_cross_encoder = None
_cross_encoder_failed = False


def _load_cross_encoder():
    global _cross_encoder, _cross_encoder_failed
    if _cross_encoder is not None or _cross_encoder_failed:
        return _cross_encoder
    try:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        _cross_encoder = TextCrossEncoder(RERANK_MODEL, cache_dir=FASTEMBED_CACHE)
    except Exception:  # noqa: BLE001
        _cross_encoder_failed = True
        _cross_encoder = None
    return _cross_encoder


def _fastembed_scores(query: str, texts: list[str]) -> list[float] | None:
    encoder = _load_cross_encoder()
    if encoder is None:
        return None
    try:
        scores = list(encoder.rerank(query, texts))
        return [float(score) for score in scores]
    except Exception:  # noqa: BLE001
        return None


def _llm_scores(query: str, texts: list[str]) -> list[float] | None:
    try:
        from src.agent.config import get_llm

        numbered = "\n".join(
            f"[{index + 1}] {text[:600]}" for index, text in enumerate(texts)
        )
        prompt = (
            "你是采购知识库的检索重排器。根据问题判断每个片段的相关性，"
            "0 表示无关，100 表示直接回答。只输出 JSON："
            '{"scores":[{"i":1,"score":80}]}\n\n'
            f"问题：{query}\n\n片段：\n{numbered}"
        )
        response = get_llm(thinking=False).invoke(prompt)
        content = str(getattr(response, "content", "") or "")
        match = re.search(r"\{.*\}", content, re.S)
        if not match:
            return None
        payload = json.loads(match.group(0))
        result = [0.0] * len(texts)
        for row in payload.get("scores", []):
            index = int(row.get("i", 0)) - 1
            if 0 <= index < len(texts):
                result[index] = max(0.0, min(100.0, float(row.get("score", 0)))) / 100.0
        return result
    except Exception:  # noqa: BLE001
        return None


def rerank(query: str, texts: list[str]) -> list[float] | None:
    """返回与 texts 对齐的 0~1 相关性分数；不可用时返回 None。"""
    if not texts or RERANKER == "none":
        return None
    if RERANKER in {"auto", "fastembed"}:
        scores = _fastembed_scores(query, texts)
        if scores is not None:
            return scores
    if RERANKER in {"auto", "llm"}:
        return _llm_scores(query, texts)
    return None
