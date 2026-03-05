import logging

from app.config import get_settings

logger = logging.getLogger(__name__)

_model = None


def get_model():
    """Lazily load and cache the SentenceTransformer embedding model."""
    global _model
    if _model is not None:
        return _model

    settings = get_settings()
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

        device = _detect_device()
        logger.info(
            "Loading embedding model '%s' on device '%s'",
            settings.embedding_model,
            device,
        )
        _model = SentenceTransformer(settings.embedding_model, device=device)
        logger.info("Embedding model loaded successfully")
    except ImportError:
        logger.warning(
            "sentence_transformers not installed; falling back to zero-vector embeddings"
        )
        _model = None
    except Exception as exc:
        logger.error("Failed to load embedding model: %s", exc)
        _model = None
    return _model


def _detect_device() -> str:
    """Detect available compute device (CUDA > MPS > CPU)."""
    try:
        import torch  # type: ignore[import-untyped]

        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


def embed_chunks(
    chunks: list[dict], batch_size: int = 64
) -> list[tuple[str, list[float]]]:
    """
    Embed a list of chunk dicts in batches.

    Each chunk must have 'id' and 'text' keys.
    Returns list of (chunk_id, vector) pairs.
    """
    if not chunks:
        return []

    model = get_model()

    texts = [chunk["text"] for chunk in chunks]
    chunk_ids = [chunk["id"] for chunk in chunks]

    if model is None:
        logger.warning("No embedding model available; returning zero vectors")
        zero_vec: list[float] = [0.0] * 384
        return [(cid, zero_vec) for cid in chunk_ids]

    results: list[tuple[str, list[float]]] = []
    try:
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            batch_ids = chunk_ids[i : i + batch_size]
            vectors = model.encode(batch_texts, show_progress_bar=False)
            for cid, vec in zip(batch_ids, vectors):
                results.append((cid, vec.tolist()))
        logger.debug("Embedded %d chunks", len(results))
    except Exception as exc:
        logger.error("Error during chunk embedding: %s", exc)
        zero_vec = [0.0] * 384
        results = [(cid, zero_vec) for cid in chunk_ids]

    return results


def embed_query(query: str) -> list[float]:
    """Embed a single query string and return the vector."""
    model = get_model()
    if model is None:
        logger.warning("No embedding model available; returning zero vector for query")
        return [0.0] * 384
    try:
        vector = model.encode([query], show_progress_bar=False)
        return vector[0].tolist()
    except Exception as exc:
        logger.error("Error embedding query: %s", exc)
        return [0.0] * 384
