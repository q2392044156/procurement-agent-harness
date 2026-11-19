"""入库增强的测试：DOCX 表格、扫描件 OCR、结构化切分、BM25 稀疏向量。

OCR 用例依赖 rapidocr_onnxruntime 与系统中文字体；任一缺失即 skip，不阻塞其余用例。
"""
from pathlib import Path

import pytest

from src.kb.bm25 import build_stats, doc_sparse, query_sparse, tokenize
from src.kb.chunker import chunk_pages
from src.kb.parser import parse_document


def _write_docx(path: Path) -> Path:
    """生成一份带标题与表格的 DOCX，用于验证表格转 Markdown。"""
    from docx import Document

    doc = Document()
    doc.add_heading("供应商准入要求", level=1)
    doc.add_paragraph("供应商必须提供营业执照与质量体系证书。")
    table = doc.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "资质"
    table.rows[0].cells[1].text = "有效期"
    table.rows[1].cells[0].text = "ISO9001"
    table.rows[1].cells[1].text = "3年"
    doc.save(path)
    return path


def test_docx_heading_and_table(tmp_path):
    """DOCX 的标题与表格都要进正文，表格转成 Markdown 管道格式。"""
    pages = parse_document(_write_docx(tmp_path / "table.docx"))
    text = "\n".join(page[1] for page in pages)
    assert "供应商准入要求" in text
    assert "ISO9001" in text
    assert "| 资质 | 有效期 |" in text


def test_scanned_pdf_ocr(tmp_path):
    """扫描件 PDF（图片无文字层）走 OCR 才能拿到内容。"""
    pytest.importorskip("rapidocr_onnxruntime", reason="OCR 引擎 rapidocr_onnxruntime 未安装")
    pytest.importorskip("pymupdf", reason="pymupdf 未安装")
    from PIL import Image, ImageDraw, ImageFont
    import pymupdf

    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    if not font_path.exists():
        pytest.skip("缺少中文字体 msyh.ttc，无法生成可识别扫描件")

    image = Image.new("RGB", (1200, 300), "white")
    ImageDraw.Draw(image).text(
        (40, 100), "付款账期为月结30天，质保期12个月。",
        fill="black", font=ImageFont.truetype(str(font_path), 36),
    )
    image_path = tmp_path / "scan.png"
    image.save(image_path)

    pdf_path = tmp_path / "scan.pdf"
    pdf = pymupdf.open()
    page = pdf.new_page(width=600, height=300)
    page.insert_image(pymupdf.Rect(0, 0, 600, 300), filename=str(image_path))
    pdf.save(pdf_path)
    pdf.close()

    ocr_text = "\n".join(text for _, text in parse_document(pdf_path))
    assert "月结" in ocr_text and "30" in ocr_text, ocr_text[:300]


def test_long_document_chunking():
    """长文档按章节切分，章节标题要保留在 chunk 上。"""
    long_pages = [(1, "\n\n".join([
        "第一章 总则\n\n" + "采购制度说明。" * 80,
        "第二章 审批\n\n" + "审批流程说明。" * 80,
    ]))]
    chunks = chunk_pages(long_pages)
    assert len(chunks) >= 2
    assert any(chunk.get("section", "").startswith("第一章") for chunk in chunks)


def test_bm25_stats_and_sparse(tmp_path):
    """BM25 统计要含 N 与 idf；中英混排按字切词，英文整体小写保留。"""
    texts = [page[1] for page in parse_document(_write_docx(tmp_path / "bm25.docx"))]
    stats = build_stats(texts)
    assert stats["N"] == len(texts)
    assert stats["idf"]

    indices, values = doc_sparse(texts[0], stats)
    q_indices, q_values = query_sparse("供应商资质", stats)
    assert indices and values and q_indices and q_values
    assert tokenize("ISO9001 供应商")[:2] == ["iso9001", "供应"]
