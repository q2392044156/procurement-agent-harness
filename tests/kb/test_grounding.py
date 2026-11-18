"""引用/拒答校验的单元测试。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.kb.grounding import enforce, validate  # noqa: E402

CHUNKS = [
    {"title": "内部采购管理制度", "page": 2},
    {"title": "采购合同管理办法", "page": 1},
]

ok = validate("付款账期为月结30天[《内部采购管理制度》第2页]", CHUNKS)
assert ok["grounded"] and not ok["invalid"], ok

bad = validate("付款账期为月结30天[《不存在的文档》第9页]", CHUNKS)
assert bad["invalid"] == ["《不存在的文档》第9页"], bad

missing = validate("付款账期为月结30天", CHUNKS)
assert not missing["hasCitation"], missing

filled = enforce("付款账期为月结30天", ["《内部采购管理制度》第2页"], empty=False)
assert "依据：" in filled and "《内部采购管理制度》第2页" in filled, filled

refused = enforce("付款账期是月结30天", [], empty=True)
assert "知识库中没有找到依据" in refused, refused

print("RAG GROUNDING: PASS (3 asserts)")
