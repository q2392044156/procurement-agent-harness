"""引用与拒答校验：确保知识库回答可追溯、无依据时不编造。"""
from __future__ import annotations

import re

CITATION_RE = re.compile(r"《([^》]+)》第(\d+)页")
REFUSAL = "知识库中没有找到依据"


def extract_citations(answer: str) -> list[str]:
    return [f"《{title}》第{page}页" for title, page in CITATION_RE.findall(answer or "")]


def validate(answer: str, chunks: list[dict]) -> dict:
    """校验答案引用是否都来自检索结果，以及是否缺少引用。"""
    valid = {
        f"《{chunk.get('title')}》第{chunk.get('page')}页"
        for chunk in chunks
        if chunk.get("title") and chunk.get("page")
    }
    citations = extract_citations(answer)
    invalid = [citation for citation in citations if citation not in valid]
    return {
        "hasCitation": bool(citations),
        "citations": citations,
        "invalid": invalid,
        "grounded": bool(citations) and not invalid,
    }


def enforce(answer: str, citations: list[str], empty: bool) -> str:
    """在流式答案末尾补齐引用或拒答声明。"""
    if not answer:
        return answer
    if empty:
        return answer if REFUSAL in answer else f"{answer}\n\n{REFUSAL}"
    if citations and not extract_citations(answer):
        unique = list(dict.fromkeys(citations))[:5]
        return f"{answer}\n\n依据：" + "；".join(unique)
    return answer
