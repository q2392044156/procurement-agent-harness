"""文档解析：PDF 按页、DOCX 按段落，返回 (页码, 文本) 列表。"""
from pathlib import Path


def parse_document(path: Path) -> list[tuple[int, str]]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _parse_pdf(path)
    if suffix in {".docx", ".doc"}:
        return _parse_docx(path)
    return [(1, path.read_text(encoding="utf-8", errors="ignore"))]


def _parse_pdf(path: Path) -> list[tuple[int, str]]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages: list[tuple[int, str]] = []
    for index, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append((index, text))
    return pages


def _parse_docx(path: Path) -> list[tuple[int, str]]:
    from docx import Document

    document = Document(str(path))
    lines: list[str] = []
    for paragraph in document.paragraphs:
        text = (paragraph.text or "").strip()
        if not text:
            continue
        style = (paragraph.style.name or "").lower() if paragraph.style else ""
        if style.startswith("heading"):
            lines.append(f"\n{'#' * min(len(style), 6)} {text}")
        else:
            lines.append(text)
    return [(1, "\n".join(lines))]
