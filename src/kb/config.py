"""RAG 配置：Qdrant、bge-m3、切分与状态文件。"""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=True)

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION = os.getenv("KB_COLLECTION", "procurement_kb")
EMBEDDING_MODEL = os.getenv("KB_EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_DEVICE = os.getenv("KB_EMBEDDING_DEVICE", "cpu")
DEFAULT_TOP_K = int(os.getenv("KB_TOP_K", "8"))
MIN_SCORE = float(os.getenv("KB_MIN_SCORE", "0.40"))
LEXICAL_WEIGHT = float(os.getenv("KB_LEXICAL_WEIGHT", "0.25"))
CHUNK_SIZE = int(os.getenv("KB_CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("KB_CHUNK_OVERLAP", "120"))
STATE_FILE = Path(os.getenv("KB_STATE_FILE", str(ROOT / ".kb_state.json")))

ERP_BASE_URL = os.getenv("ERP_BASE_URL", "http://localhost:8080")
INTERNAL_TOKEN = os.getenv("AGENT_INTERNAL_TOKEN", "")
