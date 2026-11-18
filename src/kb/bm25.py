"""轻量 BM25：中文 bigram + 英文/数字词，生成 Qdrant sparse 向量。

文档侧存长度归一化后的 TF 权重；查询侧存 IDF 权重，
点积即 BM25 分数。语料统计保存在 ``bm25_stats.json``。
"""
from __future__ import annotations

import json
import math
import re
import zlib
from collections import Counter
from pathlib import Path

from src.kb.config import BM25_STATS_FILE

K1 = 1.2
B = 0.75

_LATIN = re.compile(r"[a-z0-9]+")
_HAN = re.compile(r"[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    lower = (text or "").lower()
    tokens = _LATIN.findall(lower)
    han = _HAN.findall(lower)
    tokens.extend(han[i] + han[i + 1] for i in range(len(han) - 1))
    if len(han) == 1:
        tokens.append(han[0])
    return tokens


def term_id(term: str) -> int:
    return zlib.crc32(term.encode("utf-8")) & 0x7FFFFFFF


def _sparse(tokens: list[str], weights: dict[str, float]) -> tuple[list[int], list[float]]:
    indices: list[int] = []
    values: list[float] = []
    for term, weight in weights.items():
        if weight <= 0:
            continue
        indices.append(term_id(term))
        values.append(float(weight))
    return indices, values


def build_stats(texts: list[str]) -> dict:
    documents = [tokenize(text) for text in texts]
    total = len(documents)
    df: Counter[str] = Counter()
    for tokens in documents:
        df.update(set(tokens))
    avgdl = sum(len(tokens) for tokens in documents) / max(total, 1)
    idf = {
        term: math.log(1 + (total - freq + 0.5) / (freq + 0.5))
        for term, freq in df.items()
    }
    return {"N": total, "avgdl": avgdl, "idf": idf}


def save_stats(stats: dict, path: Path = BM25_STATS_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stats, ensure_ascii=False), encoding="utf-8")


def load_stats(path: Path = BM25_STATS_FILE) -> dict:
    if not path.exists():
        return {"N": 0, "avgdl": 1.0, "idf": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"N": 0, "avgdl": 1.0, "idf": {}}


def doc_sparse(text: str, stats: dict) -> tuple[list[int], list[float]]:
    tokens = tokenize(text)
    if not tokens:
        return [], []
    counts = Counter(tokens)
    avgdl = float(stats.get("avgdl") or 1.0) or 1.0
    length = len(tokens)
    weights = {
        term: count * (K1 + 1) / (count + K1 * (1 - B + B * length / avgdl))
        for term, count in counts.items()
    }
    return _sparse(tokens, weights)


def query_sparse(query: str, stats: dict) -> tuple[list[int], list[float]]:
    idf = stats.get("idf") or {}
    tokens = tokenize(query)
    if not tokens:
        return [], []
    default = math.log(1 + (stats.get("N", 0) + 0.5) / 0.5) if stats.get("N") else 1.0
    weights = {term: idf.get(term, default) for term in set(tokens)}
    return _sparse(tokens, weights)
