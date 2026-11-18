"""门禁：逐模块 import 冒烟 + 静态检查 src.* 导入都能落到真实文件。"""
import importlib
import io
import pathlib
import sys
import traceback

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

WEB_ENTRY = {"src.server.main", "src.mcp_server.server_main"}


def modules(pkg_dir: pathlib.Path):
    out = []
    for p in sorted(pkg_dir.rglob("*.py")):
        rel = p.relative_to(ROOT).with_suffix("")
        parts = list(rel.parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        out.append(".".join(parts))
    return out


def smoke(mods):
    ok, bad = 0, []
    for m in mods:
        try:
            importlib.import_module(m)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            bad.append((m, f"{type(exc).__name__}: {exc}"))
    return ok, bad


targets = modules(ROOT / "src") + modules(ROOT / "scripts") + modules(ROOT / "evals")
targets = [m for m in targets if m and not m.split(".")[-1].startswith("_")]
ok, bad = smoke(targets)
print(f"import smoke: ok={ok} fail={len(bad)}")
for m, e in bad[:20]:
    print("  FAIL", m, e)

# 静态检查：文件里出现的 src.xxx 导入，第一个模块段必须存在于 src/
unresolved = []
for p in list((ROOT / "src").rglob("*.py")) + list((ROOT / "tests").rglob("*.py")) \
        + list((ROOT / "scripts").rglob("*.py")) + list((ROOT / "evals").rglob("*.py")):
    for line in io.open(p, encoding="utf-8").read().splitlines():
        s = line.strip()
        if not (s.startswith("from src.") or s.startswith("import src.")):
            continue
        mod = s.split()[1] if s.startswith("from") else s.split()[1].split(",")[0]
        path = ROOT.joinpath(*mod.split("."))
        if not (path.with_suffix(".py").exists() or (path / "__init__.py").exists()):
            unresolved.append(f"{p.relative_to(ROOT)}: {s}")
print(f"static import check: unresolved={len(unresolved)}")
for u in unresolved[:20]:
    print("  ", u)
sys.exit(1 if (bad or unresolved) else 0)
