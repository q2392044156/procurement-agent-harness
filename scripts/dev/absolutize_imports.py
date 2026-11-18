"""把 src/ 与 tests/ 下的相对导入统一改写成绝对导入（一次性 codemod）。

为什么要做：后续的结构调整会移动几十个文件，而 `from ...agent.x import y`
的 `.` 数量随目录深度变化——移动文件时它不会报错，只会在 import 时才炸。
改写成 `from src.agent.x import y` 之后，任何移动都退化成了一次字符串替换，
风险从「相对深度」变成「模块路径不存在」，而后者可以被静态检查一次性找出来。

用法：python scripts/dev/absolutize_imports.py [--apply]
不带 --apply 时只打印将要做的改写。
"""
from __future__ import annotations

import ast
import io
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TARGETS = list((ROOT / "src").rglob("*.py")) + list((ROOT / "tests").rglob("*.py"))


def module_of(path: pathlib.Path) -> tuple[str, str]:
    """返回 (模块名, 所在包)。``__init__.py`` 的包就是它自己。"""
    rel = path.relative_to(ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
        return ".".join(parts), ".".join(parts)
    return ".".join(parts), ".".join(parts[:-1])


def render(level: int, module: str | None, names: list[ast.alias], package: str) -> str | None:
    pkg_parts = package.split(".") if package else []
    if level - 1 > len(pkg_parts):
        return None  # 超出仓库根，说明本身就是错的
    base = pkg_parts[: len(pkg_parts) - (level - 1)]
    if module:
        base = base + module.split(".")
    if not base:
        return None
    rendered = ", ".join(
        f"{a.name} as {a.asname}" if a.asname else a.name for a in names
    )
    return f"from {'.'.join(base)} import {rendered}"


def main() -> int:
    apply = "--apply" in sys.argv
    changed = files = comments = skipped = 0
    for path in TARGETS:
        text = io.open(path, encoding="utf-8", newline="").read()
        tree = ast.parse(text)
        _, package = module_of(path)
        edits: list[tuple[int, int, str]] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.level:
                continue
            new = render(node.level, node.module, node.names, package)
            if new is None:
                skipped += 1
                print(f"SKIP (越界) {path}: level={node.level} module={node.module}")
                continue
            original = ast.get_source_segment(text, node) or ""
            if "#" in original:
                comments += 1
            edits.append((node.lineno, node.end_lineno, new))
        if not edits:
            continue
        lines = text.splitlines(keepends=True)
        for lineno, end_lineno, new in sorted(edits, reverse=True):
            first = lines[lineno - 1]
            # 语句可能缩进在函数体内，改写后必须保持同一层缩进
            indent = first[: len(first) - len(first.lstrip())]
            # 行内注释单独保留在语句末尾
            tail = lines[end_lineno - 1].rstrip("\r\n")
            comment = tail[tail.index("#"):] if "#" in tail else ""
            lines[lineno - 1:end_lineno] = [indent + new + ("  " + comment if comment else "") + "\n"]
        new_text = "".join(lines)
        ast.parse(new_text)  # 改完必须仍可解析
        files += 1
        changed += len(edits)
        if apply:
            io.open(path, "w", encoding="utf-8", newline="").write(new_text)
        print(f"{'OK ' if apply else 'DRY'} {path.relative_to(ROOT)}: {len(edits)} 条")
    print(f"\n合计 {files} 文件 / {changed} 条相对导入；含行内注释被保留 {comments}；跳过 {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
