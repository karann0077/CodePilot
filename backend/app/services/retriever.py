import logging
from collections import Counter

from sqlalchemy.orm import Session

from app.models import Chunk
from app.services import embeddings, vector_store

logger = logging.getLogger(__name__)


def retrieve(
    query: str,
    repo_id: str,
    top_k: int = 8,
    db_session: Session | None = None,
) -> list[dict]:
    """
    Retrieve the most relevant chunks for a query from a given repo.

    Steps:
    1. Embed the query.
    2. Search vector store for top_k * 2 candidates.
    3. Enrich with chunk text from DB (if db_session provided).
    4. Rerank using vector score + keyword score + file frequency bonus.
    5. Return top_k results sorted by combined score descending.

    Each result dict: {chunk_id, file_path, start_line, end_line,
                       text, score, language}
    """
    if not query.strip():
        return []

    query_vec = embeddings.embed_query(query)
    vs = vector_store.get_vector_store()
    candidates = vs.search(query_vector=query_vec, repo_id=repo_id, top_k=top_k * 2)

    if not candidates:
        logger.info("No vector search results for repo %s", repo_id)
        return []

    # Fetch chunk texts from DB if session available
    if db_session is not None:
        chunk_ids = [c["chunk_id"] for c in candidates]
        db_chunks: dict[str, Chunk] = {
            ch.id: ch
            for ch in db_session.query(Chunk).filter(Chunk.id.in_(chunk_ids)).all()
        }
    else:
        db_chunks = {}

    query_terms = set(query.lower().split())
    file_path_counts: Counter = Counter(c["file_path"] for c in candidates)
    max_file_count = max(file_path_counts.values(), default=1)

    ranked: list[dict] = []
    for cand in candidates:
        chunk_id = cand["chunk_id"]
        db_chunk = db_chunks.get(chunk_id)
        text = db_chunk.text if db_chunk else ""
        if db_chunk and db_chunk.file:
            fallback_file_path = db_chunk.file.path
        else:
            fallback_file_path = ""
        file_path = cand.get("file_path") or fallback_file_path
        start_line = cand.get("start_line", db_chunk.start_line if db_chunk else 0)
        end_line = cand.get("end_line", db_chunk.end_line if db_chunk else 0)
        language = cand.get("language", "unknown")

        vector_score = cand.get("score", 0.0)

        # Keyword score: fraction of query terms found in chunk text
        if text and query_terms:
            text_lower = text.lower()
            matched = sum(1 for term in query_terms if term in text_lower)
            keyword_score = matched / len(query_terms)
        else:
            keyword_score = 0.0

        # File frequency bonus: top file gets 1.0, decays linearly
        file_count = file_path_counts.get(file_path, 0)
        file_bonus = file_count / max_file_count if max_file_count > 0 else 0.0

        combined = (
            vector_score * 0.6
            + keyword_score * 0.3
            + file_bonus * 0.1
        )

        ranked.append(
            {
                "chunk_id": chunk_id,
                "file_path": file_path,
                "start_line": start_line,
                "end_line": end_line,
                "text": text,
                "score": combined,
                "language": language,
            }
        )

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:top_k]
