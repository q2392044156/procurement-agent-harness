"""入库增强的单元/集成测试：OCR、DOCX 表格、结构化切分、BM25。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.kb.bm25 import build_stats, doc_sparse, query_sparse, tokenize  # noqa: E402
from src.kb.chunker import chunk_pages  # noqa: E402
from src.kb.parser import parse_document  # noqa: E402

WORK = Path(r"E:\project\my_project2\.tmp\rag_ingest_test")
WORK.mkdir(parents=True, exist_ok=True)

# 1) DOCX：标题 + 表格
from docx import Document  # noqa: E402

docx_path = WORK / "table.docx"
doc = Document()
doc.add_heading("供应商准入要求", level=1)
doc.add_paragraph("供应商必须提供营业执照与质量体系证书。")
table = doc.add_table(rows=2, cols=2)
table.rows[0].cells[0].text = "资质"
table.rows[0].cells[1].text = "有效期"
table.rows[1].cells[0].text = "ISO9001"
table.rows[1].cells[1].text = "3年"
doc.save(docx_path)
pages = parse_document(docx_path)
text = "\n".join(page[1] for page in pages)
assert "ISO9001" in text and "| 资质 | 有效期 |" in text, text[:300]

# 2) 扫描件 PDF：文字先渲染为图片，再 OCR
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
import fitz  # noqa: E402

font_path = "C:/Windows/Fonts/msyh.ttc"
font = ImageFont.truetype(font_path, 36)
image = Image.new("RGB", (1200, 300), "white")
draw = ImageDraw.Draw(image)
draw.text((40, 100), "付款账期为月结30天，质保期12个月。", fill="black", font=font)
image_path = WORK / "scan.png"
image.save(image_path)

pdf_path = WORK / "scan.pdf"
pdf = fitz.open()
page = pdf.new_page(width=600, height=300)
page.insert_image(fitz.Rect(0, 0, 600, 300), filename=str(image_path))
pdf.save(pdf_path)
ocr_pages = parse_document(pdf_path)
ocr_text = "\n".join(text for _, text in ocr_pages)
assert "月结" in ocr_text and "30" in ocr_text, ocr_text[:300]

# 3) 长文档结构化切分：多段、带章节
long_pages = [(1, "\n\n".join(
    ["第一章 总则\n\n" + "采购制度说明。" * 80, "第二章 审批\n\n" + "审批流程说明。" * 80]
))]
chunks = chunk_pages(long_pages)
assert len(chunks) >= 2, len(chunks)
assert any(chunk.get("section", "").startswith("第一章") for chunk in chunks), chunks

# 4) BM25 统计与稀疏向量
texts = [page[1] for page in pages] + [ocr_text]
stats = build_stats(texts)
assert stats["N"] == len(texts) and stats["idf"], stats
indices, values = doc_sparse(texts[0], stats)
q_indices, q_values = query_sparse("供应商资质", stats)
assert indices and values and q_indices and q_values
assert tokenize("ISO9001 供应商")[:2] == ["iso9001", "供应"]

print(f"RAG INGESTION: PASS (chunks={len(chunks)}, ocrChars={len(ocr_text)}, "
      f"bm25Terms={len(stats['idf'])})")
