"""RAG 评测：45 个可回答问题 + 5 个无关问题。

指标：Top1 命中率、Top5 命中率、关键词命中率、无关问题拒答率。
用法：conda run -n procurement python scripts/eval_rag.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.kb.retriever import search  # noqa: E402

MANIFEST = ROOT / "samples" / "kb_corpus" / "manifest.json"

EXISTING = [
    ("内部采购管理制度", "采购管理制度的目的和适用范围是什么？", ""),
    ("内部采购管理制度", "采购申请需要经过哪些审批角色？", ""),
    ("内部采购管理制度", "采购订单的付款条件如何约定？", ""),
    ("供应商准入与绩效评价管理办法", "供应商准入需要提交哪些资质材料？", ""),
    ("供应商准入与绩效评价管理办法", "供应商绩效评价包括哪些维度？", ""),
    ("供应商准入与绩效评价管理办法", "供应商出现重大质量问题会如何处理？", ""),
]

EXTRA = [
    ("合同累计变更金额超过多少需要重新审批？", "合同履约与变更管理办法", "10%"),
    ("盘点差异率超过多少需要编制差异分析报告？", "库存盘点管理办法", "1%"),
    ("列入黑名单的供应商几年内不得重新准入？", "供应商退出管理办法", "3年"),
]


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cases: list[dict] = []
    for doc in manifest["documents"]:
        for item in doc["questions"]:
            cases.append({"q": item["q"], "title": doc["title"], "keyword": item["keyword"]})
    for title, question, keyword in EXISTING:
        cases.append({"q": question, "title": title, "keyword": keyword})
    for question, title, keyword in EXTRA:
        cases.append({"q": question, "title": title, "keyword": keyword})
    unrelated = manifest.get("unrelated") or []

    top1 = top5 = keyword_hits = 0
    failures: list[str] = []
    for case in cases:
        result = search(case["q"], "1", 5)["data"]["results"]
        titles = [row["title"] for row in result]
        hit1 = bool(titles) and titles[0] == case["title"]
        hit5 = case["title"] in titles
        keyword_hit = (
            not case["keyword"]
            or any(case["keyword"] in row["text"] for row in result if row["title"] == case["title"])
        )
        top1 += int(hit1)
        top5 += int(hit5)
        keyword_hits += int(keyword_hit)
        if not hit5:
            failures.append(f"[{case['title']}] {case['q']} -> {titles[:3]}")

    refused = 0
    for question in unrelated:
        result = search(question, "1", 5)["data"]["results"]
        refused += int(len(result) == 0)

    total = len(cases)
    print(f"answerable: {total}, unrelated: {len(unrelated)}")
    print(f"top1: {top1}/{total} = {top1 / total:.1%}")
    print(f"top5: {top5}/{total} = {top5 / total:.1%}")
    print(f"keyword: {keyword_hits}/{total} = {keyword_hits / total:.1%}")
    print(f"refusal: {refused}/{len(unrelated)} = {refused / max(len(unrelated), 1):.0%}")
    if failures:
        print("\nfailures:")
        for line in failures[:15]:
            print("  -", line)

    passed = top5 / total >= 0.9 and refused == len(unrelated)
    print(f"\nRAG EVAL: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
