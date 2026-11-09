"""文档解析：PDF 按页（含表格/OCR）、DOCX 按段落与表格。"""
from pathlib import Path

_ocr_engine = None


def parse_document(path: Path) -> list[tuple[int, str]]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _parse_pdf(path)
    if suffix in {".docx", ".doc"}:
        return _parse_docx(path)
    return [(1, path.read_text(encoding="utf-8", errors="ignore"))]


def _parse_pdf(path: Path) -> list[tuple[int, str]]:
    from pypdf import PdfReader

    page_texts: dict[int, str] = {}
    reader = PdfReader(str(path))
    for index, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if not text:
            text = _ocr_page(path, index)
        page_texts[index] = text

    try:
        import pdfplumber

        with pdfplumber.open(str(path)) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                tables = page.extract_tables() or []
                if tables:
                    page_texts[index] = (page_texts.get(index, "") + "\n" + _tables_markdown(tables)).strip()
    except Exception:  # noqa: BLE001
        pass

    return [(page, text) for page, text in page_texts.items() if text]


def _ocr_page(path: Path, page_number: int) -> str:
    global _ocr_engine
    try:
        import fitz
        from rapidocr_onnxruntime import RapidOCR

        if _ocr_engine is None:
            _ocr_engine = RapidOCR()
        document = fitz.open(str(path))
        page = document[page_number - 1]
        pixmap = page.get_pixmap(dpi=200)
        import numpy as np

        image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
            pixmap.height, pixmap.width, pixmap.n
        )
        result, _ = _ocr_engine(image)
        return "\n".join(str(line[1]) for line in (result or []))
    except Exception:  # noqa: BLE001
        return ""


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

    for table in document.tables:
        rows = []
        for row in table.rows:
            cells = [((cell.text or "").strip().replace("\n", " ")) for cell in row.cells]
            if any(cells):
                rows.append("| " + " | ".join(cells) + " |")
        if rows:
            header = "| " + " | ".join(f"列{i + 1}" for i in range(len(table.rows[0].cells))) + " |"
            lines.append("\n" + header + "\n" + "\n".join(rows))
    return [(1, "\n".join(lines))]


def _tables_markdown(tables) -> str:
    blocks = []
    for table in tables:
        rows = []
        for row in table:
            cells = [((cell or "").strip().replace("\n", " ")) for cell in row]
            if any(cells):
                rows.append("| " + " | ".join(cells) + " |")
        if rows:
            blocks.append("\n".join(rows))
    return "\n\n".join(blocks)
