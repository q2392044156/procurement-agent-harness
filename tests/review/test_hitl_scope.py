"""验证写操作 HITL 覆盖主 Agent 与子 Agent。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.agent.config import INTERRUPT_ON_TOOLS  # noqa: E402
from src.agent.subagents.loader import load_subagent_configs, resolve_subagent_tools  # noqa: E402


class FakeTool:
    def __init__(self, name: str):
        self.name = name


REQUIRED = {
    "order_create", "order_update", "order_submit", "order_close", "order_cancel",
    "requisition_create", "requisition_submit", "requisition_cancel", "requisition_convert",
}


def main() -> int:
    assert REQUIRED.issubset(INTERRUPT_ON_TOOLS), INTERRUPT_ON_TOOLS
    fake_tools = [FakeTool(name) for name in sorted(REQUIRED)]
    specs = resolve_subagent_tools(load_subagent_configs(), fake_tools)
    assert specs, "no subagent specs loaded"
    for spec in specs:
        interrupt_on = spec.get("interrupt_on") or {}
        missing = REQUIRED - set(interrupt_on)
        assert not missing, f"{spec['name']} missing HITL: {sorted(missing)}"
        print(f"PASS {spec['name']}: {sorted(interrupt_on)}")
    print(f"HITL SCOPE: PASS (main + {len(specs)} subagents, {len(REQUIRED)} write tools)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
