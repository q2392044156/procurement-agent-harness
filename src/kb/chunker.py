"""结构化切分：按页、按段落/标题合并，保留页码与章节。"""
import re

from src.kb.config import CHUNK_OVERLAP, CHUNK_SIZE

_HEADING = re.compile(r"^(#{1,6}\s+|第[一二三四五六七八九十百]+[章节条]\s*|[一二三四五六七八九十]+、|\d+\.\s+)")
_SENTENCE = re.compile(r"(?<=[。！？；.!?;])")


def chunk_pages(pages: list[tuple[int, str]]) -> list[dict]:
    chunks: list[dict] = []
    for page, text in pages:
        blocks = _blocks(_normalize(text))
        buffer = ""
        section = ""
        for block in blocks:
            if _HEADING.match(block):
                section = block.lstrip("# ").strip()[:80]
            candidate = f"{buffer}\n{block}".strip() if buffer else block
            if len(candidate) <= CHUNK_SIZE:
                buffer = candidate
                continue
            if buffer:
                chunks.append(_chunk(buffer, page, section))
            overlap = buffer[-CHUNK_OVERLAP:] if buffer else ""
            buffer = (overlap + "\n" + block).strip() if overlap else block
            if len(buffer) > CHUNK_SIZE:
                for piece in _split_long(buffer):
                    chunks.append(_chunk(piece, page, section))
                buffer = ""
        if buffer:
            chunks.append(_chunk(buffer, page, section))
    return chunks


def _chunk(text: str, page: int, section: str) -> dict:
    headings = [
        line.strip()[:80]
        for line in text.splitlines()
        if _HEADING.match(line.strip())
    ]
    return {
        "page": page,
        "section": headings[-1] if headings else (section or None),
        "text": text.strip(),
    }


def _blocks(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if _HEADING.match(stripped) and current:
            blocks.append("\n".join(current).strip())
            current = [stripped]
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current).strip())

    expanded: list[str] = []
    for block in blocks:
        if not block:
            continue
        if len(block) <= CHUNK_SIZE:
            expanded.append(block)
        else:
            expanded.extend(_split_long(block))
    return expanded


def _split_long(text: str) -> list[str]:
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            window = text[start:end]
            cut = max(window.rfind(marker) for marker in ("\n", "。", "；", "！", "？", "，"))
            if cut > len(window) * 0.5:
                end = start + cut + 1
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= len(text):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return pieces


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
