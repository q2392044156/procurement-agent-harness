"""仓库内路径的唯一来源。

所有需要「仓库根 / 技能目录 / 提示词目录」的模块都从这里取，
不要在各自文件里再写一遍 ``Path(__file__).parent.parent...``——
那种写法在文件被移动后不会报错，只会静默指向错误的位置。
"""
from pathlib import Path

#: 仓库根目录（本文件位于 <root>/src/core/paths.py）
PROJECT_ROOT = Path(__file__).resolve().parents[2]

#: 源码根目录
SRC_DIR = PROJECT_ROOT / "src"

#: 技能内容目录：curated 的 SKILL.md 与附属脚本，随镜像/沙箱分发，不被 import
SKILLS_DIR = PROJECT_ROOT / "skills"

#: 提示词目录（AGENTS.md 等）
PROMPTS_DIR = SRC_DIR / "agent" / "prompts"

__all__ = ["PROJECT_ROOT", "SRC_DIR", "SKILLS_DIR", "PROMPTS_DIR"]
