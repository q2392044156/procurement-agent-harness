"""S5 阶段门禁：记忆闭环 + 技能库。

覆盖：
- MongoDBStore 真实落盘：偏好写入/读取、用户隔离、改口历史、偏好字典
- 技能目录：6 个采购技能可发现、可读取正文、目录元数据可用
- 记忆工具开关与配置

用法：conda run -n procurement python scripts/verify_phase_s5.py
"""
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=True)

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    return ok


def main() -> int:
    from src.agent.memory import MemoryKeeper
    from src.agent.progressive_skills import SkillCatalog
    from src.infra.mongodb_store import MongoDBStore

    uid = f"s5-gate-{uuid.uuid4().hex[:8]}"
    store = MongoDBStore(
        uri="mongodb://localhost:27017",
        db_name="erp_agent",
        collection_name="s5_gate_store",
    )
    keeper = MemoryKeeper(store, uid)

    check("mongo store available", keeper.available)

    keeper.upsert_semantic("preferred_chart_type", "bar")
    item = keeper.active_semantic("preferred_chart_type")
    check("memory write/read", item is not None and item.content == "bar",
          f"content={getattr(item, 'content', None)}")

    other = MemoryKeeper(store, f"{uid}-other")
    check("user isolation", other.active_semantic("preferred_chart_type") is None)

    keeper.upsert_semantic("preferred_chart_type", "line")
    active = keeper.active_semantic("preferred_chart_type")
    history = keeper.semantic_history("preferred_chart_type")
    check("preference change keeps history",
          active is not None and active.content == "line" and len(history) >= 2,
          f"active={getattr(active, 'content', None)} history={len(history)}")

    keeper.save_preferences({"preferred_output": "excel", "preferred_currency": "CNY"})
    preferences = keeper.load_preferences()
    check("preferences map persisted",
          preferences.get("preferred_output") == "excel"
          and preferences.get("preferred_currency") == "CNY",
          json.dumps(preferences, ensure_ascii=False)[:80])

    keeper.upsert_semantic("contact_note", "电话13800138000 邮箱buyer@example.com")
    contact = keeper.active_semantic("contact_note")
    check("pii redaction",
          contact is not None
          and "13800138000" not in contact.content
          and "buyer@example.com" not in contact.content
          and "[REDACTED]" in contact.content,
          f"content={getattr(contact, 'content', None)}")

    catalog = SkillCatalog(ROOT / "skills", store=store, user_id=uid)
    entries, warnings = catalog.entries()
    ids = [entry["id"] for entry in entries]
    required = [
        "supplier-analysis",
        "price-comparison",
        "inventory-optimizer",
        "report-generator",
        "approval-summary",
        "procurement-analysis",
    ]
    missing = [name for name in required if not any(name in skill_id for skill_id in ids)]
    check("skill catalog", not missing, f"skills={len(entries)} missing={missing or 'none'}")

    text, location = catalog.read("builtin/procurement/supplier-analysis/SKILL.md")
    check("skill body readable",
          "supplier_scorecard" in text and "供应商分析" in text,
          f"location={location}")

    text2, _ = catalog.read("builtin/procurement/approval-summary/SKILL.md")
    check("approval skill has tools", "workflow_todo" in text2 and "approval_sla" in text2)

    index = catalog.index()
    check("skill index metadata", "supplier-analysis" in index and "approval-summary" in index,
          f"chars={len(index)} warnings={len(warnings)}")

    for mem_type in ("semantic", "episodic"):
        for memory in keeper.list_items(mem_type):
            keeper.delete(memory)

    failed = [name for name, ok, _ in RESULTS if not ok]
    print()
    print(f"PHASE S5: {'PASS' if not failed else 'FAIL'} ({len(RESULTS) - len(failed)}/{len(RESULTS)})")
    if failed:
        print("failed:", ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
