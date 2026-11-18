"""知识库增量入库 CLI。

用法：conda run -n procurement python scripts/kb_ingest.py [user_id]
"""
import json
import sys
from pathlib import Path

from src.core.paths import PROJECT_ROOT as ROOT

from src.kb.sync import sync  # noqa: E402

if __name__ == "__main__":
    user_id = sys.argv[1] if len(sys.argv) > 1 else "1"
    print(json.dumps(sync(user_id), ensure_ascii=False, indent=2))
