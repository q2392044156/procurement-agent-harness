"""按映射表移动模块并重写全仓 ``src.*`` 导入（一次性 codemod，P4 分阶段复用）。

用法：
    python scripts/dev/move_modules.py <plan.json> [--apply]

plan.json：
    {
      "moves": [["src/agent/config.py", "src/core/settings.py"], ...],
      "extra": [["src.core.settings", "src.core.settings"]],   // 拆分/改名等无法从路径推导的
      "docs":  [["from src.core.settings import", "from src.core.settings import"]]  // 可选，纯文本替换
    }

处理顺序：先 git mv（保留历史），再用「最长的旧模块名优先」做正则替换，
避免 src.core.settings 抢在 src.agent.config_extra 前面把后者改坏。
"""
from __future__ import annotations

import io
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCAN_SUFFIXES = {".py"}


def module_of(rel_path: str) -> str:
    p = pathlib.Path(rel_path).with_suffix("")
    parts = list(p.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def git_mv(old: str, new: str) -> None:
    target = ROOT / new
    target.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "mv", old, new], cwd=ROOT, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise SystemExit(f"git mv {old} -> {new} 失败:\n{result.stderr}")


def rewrite(pairs: list[tuple[str, str]], apply: bool) -> int:
    # 长模块名优先，避免前缀冲突
    pairs = sorted(pairs, key=lambda kv: len(kv[0]), reverse=True)
    patterns = [
        (re.compile(rf"\b{re.escape(old)}\b"), new) for old, new in pairs
    ]
    touched = 0
    for path in sorted(ROOT.rglob("*.py")):
        if any(part in {".venv", ".git", ".tmp", "__pycache__"} for part in path.parts):
            continue
        if path.suffix not in SCAN_SUFFIXES:
            continue
        text = io.open(path, encoding="utf-8", newline="").read()
        new_text = text
        for pattern, repl in patterns:
            new_text = pattern.sub(repl, new_text)
        if new_text != text:
            touched += 1
            if apply:
                io.open(path, "w", encoding="utf-8", newline="").write(new_text)
            print(f"  {path.relative_to(ROOT)}")
    return touched


def main() -> int:
    plan_path = ROOT / sys.argv[1]
    apply = "--apply" in sys.argv
    plan = json.loads(io.open(plan_path, encoding="utf-8").read())

    moves = plan.get("moves", [])
    derived = [(module_of(old), module_of(new)) for old, new in moves]
    pairs = derived + [tuple(x) for x in plan.get("extra", [])]

    print(f"移动 {len(moves)} 个文件，重写 {len(pairs)} 组模块名")
    if apply:
        for old, new in moves:
            git_mv(old, new)
    for old, new in pairs:
        print(f"  {old}  ->  {new}")

    touched = rewrite(pairs, apply)
    print(f"{'改写' if apply else '将改写'} {touched} 个 py 文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
