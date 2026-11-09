"""bge-m3 向量化（本地 CPU，惰性加载）。"""
import os

from .config import EMBEDDING_DEVICE, EMBEDDING_MODEL

_model = None


def get_model():
    global _model
    if _model is None:
        # hf-mirror 在 config 加载 .env 时已生效
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(EMBEDDING_MODEL, device=EMBEDDING_DEVICE)
    return _model


def dimension() -> int:
    model = get_model()
    getter = getattr(model, "get_embedding_dimension", None) or getattr(
        model, "get_sentence_embedding_dimension"
    )
    return getter()


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    vectors = get_model().encode(
        texts,
        batch_size=8,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return [vector.tolist() for vector in vectors]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
