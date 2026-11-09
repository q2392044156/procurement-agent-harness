"""按页切分文本，保留页码用于引用。"""
import re

from .config import CHUNK_OVERLAP, CHUNK_SIZE


def chunk_pages(pages: list[tuple[int, str]]) -> list[dict]:
    chunks: list[dict] = []
    for page, text in pages:
        normalized = _normalize(text)
        if not normalized:
            continue
        start = 0
        while start < len(normalized):
            end = min(start + CHUNK_SIZE, len(normalized))
            if end < len(normalized):
                end = _safe_cut(normalized, start, end)
            piece = normalized[start:end].strip()
            if piece:
                chunks.append({"page": page, "text": piece})
            if end >= len(normalized):
                break
            start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _safe_cut(text: str, start: int, end: int) -> int:
    window = text[start:end]
    for marker in ("\n\n", "\n", "。", "；", "，"):
        index = window.rfind(marker)
        if index > len(window) * 0.5:
            return start + index + len(marker)
    return end
