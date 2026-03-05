import logging
from uuid import uuid4

from app.config import get_settings

logger = logging.getLogger(__name__)

_COLLECTION = "codepilot"
_DIM = 384


def _faiss_dist_to_score(dist: float) -> float:
    """Convert L2 distance to a [0, 1] similarity score.

    Uses the formula 1/(1+dist) so that dist=0 → score=1.0 and
    score decreases monotonically.  Note this is NOT comparable to
    Qdrant's cosine similarity, but is internally consistent.
    """
    return 1.0 / (1.0 + dist)


class VectorStore:
    """Abstraction over Qdrant (preferred) with FAISS in-memory fallback."""

    def __init__(
        self, host: str, port: int, collection_name: str = _COLLECTION
    ) -> None:
        self._host = host
        self._port = port
        self._collection = collection_name
        self._client = None
        self.use_qdrant: bool = False

        # FAISS fallback state
        self._faiss_index = None
        self._faiss_meta: list[dict] = []

        self._try_qdrant()
        if not self.use_qdrant:
            self._init_faiss()

    # ------------------------------------------------------------------
    # Qdrant
    # ------------------------------------------------------------------

    def _try_qdrant(self) -> None:
        try:
            from qdrant_client import QdrantClient  # type: ignore[import-untyped]
            from qdrant_client.http import models as qm  # type: ignore[import-untyped]

            client = QdrantClient(host=self._host, port=self._port, timeout=5)
            # Verify connection
            client.get_collections()
            self._client = client
            self.use_qdrant = True
            logger.info("Qdrant connected at %s:%s", self._host, self._port)
            self._ensure_collection(_DIM)
        except Exception as exc:
            logger.warning("Qdrant unavailable, using FAISS fallback: %s", exc)

    def _ensure_collection(self, dim: int) -> None:
        try:
            from qdrant_client.http import models as qm  # type: ignore[import-untyped]

            existing = [c.name for c in self._client.get_collections().collections]
            if self._collection not in existing:
                self._client.create_collection(
                    collection_name=self._collection,
                    vectors_config=qm.VectorParams(
                        size=dim, distance=qm.Distance.COSINE
                    ),
                )
                logger.info("Created Qdrant collection '%s'", self._collection)
        except Exception as exc:
            logger.error("Failed to ensure Qdrant collection: %s", exc)

    def upsert(self, vectors: list[dict]) -> None:
        """
        Upsert vectors.

        Each dict: {id, vector, chunk_id, repo_id, file_path,
                    start_line, end_line, language}
        """
        if not vectors:
            return
        if self.use_qdrant and self._client is not None:
            self._qdrant_upsert(vectors)
        else:
            self._faiss_upsert(vectors)

    def _qdrant_upsert(self, vectors: list[dict]) -> None:
        try:
            from qdrant_client.http import models as qm  # type: ignore[import-untyped]

            points = [
                qm.PointStruct(
                    id=v.get("id") or str(uuid4()),
                    vector=v["vector"],
                    payload={
                        "chunk_id": v.get("chunk_id", ""),
                        "repo_id": v.get("repo_id", ""),
                        "file_path": v.get("file_path", ""),
                        "start_line": v.get("start_line", 0),
                        "end_line": v.get("end_line", 0),
                        "language": v.get("language", "unknown"),
                    },
                )
                for v in vectors
            ]
            self._client.upsert(collection_name=self._collection, points=points)
            logger.debug("Upserted %d vectors to Qdrant", len(points))
        except Exception as exc:
            logger.error("Qdrant upsert error: %s", exc)

    def search(
        self,
        query_vector: list[float],
        repo_id: str | None = None,
        top_k: int = 8,
        language: str | None = None,
    ) -> list[dict]:
        """Search for nearest neighbors, optionally filtered by repo_id/language."""
        if self.use_qdrant and self._client is not None:
            return self._qdrant_search(query_vector, repo_id, top_k, language)
        return self._faiss_search(query_vector, repo_id, top_k, language)

    def _qdrant_search(
        self,
        query_vector: list[float],
        repo_id: str | None,
        top_k: int,
        language: str | None,
    ) -> list[dict]:
        try:
            from qdrant_client.http import models as qm  # type: ignore[import-untyped]

            query_filter = None
            conditions = []
            if repo_id:
                conditions.append(
                    qm.FieldCondition(
                        key="repo_id", match=qm.MatchValue(value=repo_id)
                    )
                )
            if language:
                conditions.append(
                    qm.FieldCondition(
                        key="language", match=qm.MatchValue(value=language)
                    )
                )
            if conditions:
                query_filter = qm.Filter(must=conditions)

            hits = self._client.search(
                collection_name=self._collection,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=top_k,
            )
            return [
                {
                    "chunk_id": h.payload.get("chunk_id", ""),
                    "repo_id": h.payload.get("repo_id", ""),
                    "file_path": h.payload.get("file_path", ""),
                    "start_line": h.payload.get("start_line", 0),
                    "end_line": h.payload.get("end_line", 0),
                    "language": h.payload.get("language", "unknown"),
                    "score": h.score,
                }
                for h in hits
            ]
        except Exception as exc:
            logger.error("Qdrant search error: %s", exc)
            return []

    def delete_repo(self, repo_id: str) -> None:
        """Delete all vectors for a given repo_id."""
        if self.use_qdrant and self._client is not None:
            self._qdrant_delete_repo(repo_id)
        else:
            self._faiss_delete_repo(repo_id)

    def _qdrant_delete_repo(self, repo_id: str) -> None:
        try:
            from qdrant_client.http import models as qm  # type: ignore[import-untyped]

            self._client.delete(
                collection_name=self._collection,
                points_selector=qm.FilterSelector(
                    filter=qm.Filter(
                        must=[
                            qm.FieldCondition(
                                key="repo_id", match=qm.MatchValue(value=repo_id)
                            )
                        ]
                    )
                ),
            )
            logger.info("Deleted Qdrant vectors for repo %s", repo_id)
        except Exception as exc:
            logger.error("Qdrant delete_repo error: %s", exc)

    # ------------------------------------------------------------------
    # FAISS fallback
    # ------------------------------------------------------------------

    def _init_faiss(self) -> None:
        try:
            import faiss  # type: ignore[import-untyped]
            import numpy as np  # type: ignore[import-untyped]

            self._faiss_index = faiss.IndexFlatL2(_DIM)
            self._faiss_meta = []
            logger.info("FAISS in-memory index initialised (dim=%d)", _DIM)
        except ImportError:
            logger.warning("FAISS not installed; vector search will return empty results")
            self._faiss_index = None

    def _faiss_upsert(self, vectors: list[dict]) -> None:
        if self._faiss_index is None:
            return
        try:
            import numpy as np  # type: ignore[import-untyped]

            vecs = np.array([v["vector"] for v in vectors], dtype="float32")
            self._faiss_index.add(vecs)
            for v in vectors:
                self._faiss_meta.append(
                    {
                        "chunk_id": v.get("chunk_id", ""),
                        "repo_id": v.get("repo_id", ""),
                        "file_path": v.get("file_path", ""),
                        "start_line": v.get("start_line", 0),
                        "end_line": v.get("end_line", 0),
                        "language": v.get("language", "unknown"),
                    }
                )
            logger.debug("FAISS upsert: total %d vectors", self._faiss_index.ntotal)
        except Exception as exc:
            logger.error("FAISS upsert error: %s", exc)

    def _faiss_search(
        self,
        query_vector: list[float],
        repo_id: str | None,
        top_k: int,
        language: str | None,
    ) -> list[dict]:
        if self._faiss_index is None or self._faiss_index.ntotal == 0:
            return []
        try:
            import numpy as np  # type: ignore[import-untyped]

            qv = np.array([query_vector], dtype="float32")
            # Fetch more candidates for post-filtering
            k = min(top_k * 4, self._faiss_index.ntotal)
            distances, indices = self._faiss_index.search(qv, k)

            results: list[dict] = []
            for dist, idx in zip(distances[0], indices[0]):
                if idx < 0 or idx >= len(self._faiss_meta):
                    continue
                meta = self._faiss_meta[idx]
                if repo_id and meta["repo_id"] != repo_id:
                    continue
                if language and meta["language"] != language:
                    continue
                results.append({**meta, "score": _faiss_dist_to_score(dist)})
                if len(results) >= top_k:
                    break
            return results
        except Exception as exc:
            logger.error("FAISS search error: %s", exc)
            return []

    def _faiss_delete_repo(self, repo_id: str) -> None:
        if self._faiss_index is None:
            return
        logger.warning(
            "FAISS does not support deletion; repo %s vectors will remain", repo_id
        )


_vector_store_instance: VectorStore | None = None


def get_vector_store() -> VectorStore:
    """Return the singleton VectorStore instance."""
    global _vector_store_instance
    if _vector_store_instance is None:
        settings = get_settings()
        _vector_store_instance = VectorStore(
            host=settings.qdrant_host, port=settings.qdrant_port
        )
    return _vector_store_instance
