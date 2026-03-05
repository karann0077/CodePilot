import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models import Job, Repo
from app.schemas import IndexStartRequest, IndexStatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/index", tags=["index"])


@router.post("/start")
def start_indexing(
    body: IndexStartRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    """Start an indexing job for the given repo."""
    repo = db.query(Repo).filter(Repo.id == body.repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    job = Job(
        type="index",
        status="pending",
        repo_id=body.repo_id,
        payload={"repo_id": body.repo_id, "git_url": repo.git_url},
    )
    db.add(job)
    try:
        db.commit()
        db.refresh(job)
    except Exception as exc:
        db.rollback()
        logger.error("Failed to create index job: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create index job") from exc

    background_tasks.add_task(_run_indexing, job.id, body.repo_id, repo.git_url)
    return {"job_id": job.id}


@router.get("/status/{job_id}", response_model=IndexStatusResponse)
def get_index_status(job_id: str, db: Session = Depends(get_db)) -> IndexStatusResponse:
    """Get the status of an indexing job."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    result = job.result or {}
    progress = result.get("progress", 0.0)
    message = result.get("message", "")
    return IndexStatusResponse(
        job_id=job.id,
        status=job.status,
        progress=progress,
        message=message,
    )


def _run_indexing(job_id: str, repo_id: str, git_url: str) -> None:
    """
    Background task: run the full indexing pipeline.

    Opens its own DB session to avoid conflicts with the request session.
    """
    from app.services import chunker, embeddings, ingestion
    from app.services.vector_store import get_vector_store

    db: Session = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.error("Job %s not found in background task", job_id)
            return

        job.status = "running"
        job.result = {"progress": 0.0, "message": "Starting ingestion"}
        db.commit()

        # Step 1 – Ingestion
        logger.info("Indexing job %s: ingesting repo %s", job_id, repo_id)
        file_tuples = ingestion.ingest_repo(repo_id, git_url, db)

        job.result = {"progress": 0.2, "message": f"Ingested {len(file_tuples)} files"}
        db.commit()

        # Step 2 – Chunking
        all_chunks: list[dict] = []
        for idx, (file_id, file_path, content, language) in enumerate(file_tuples):
            try:
                chunks = chunker.chunk_file(file_id, file_path, content, language, db)
                all_chunks.extend(chunks)
            except Exception as exc:
                logger.warning("Chunking failed for %s: %s", file_path, exc)
            if (idx + 1) % 10 == 0:
                progress = 0.2 + 0.4 * ((idx + 1) / max(len(file_tuples), 1))
                job.result = {"progress": progress, "message": f"Chunked {idx + 1} files"}
                db.commit()

        job.result = {"progress": 0.6, "message": f"Created {len(all_chunks)} chunks"}
        db.commit()

        # Step 3 – Embeddings
        logger.info("Indexing job %s: embedding %d chunks", job_id, len(all_chunks))
        vectors_with_ids = embeddings.embed_chunks(all_chunks)

        # Build vector dicts for upsert
        chunk_meta: dict[str, dict] = {c["id"]: c for c in all_chunks}
        vectors: list[dict] = []
        for chunk_id, vector in vectors_with_ids:
            meta = chunk_meta.get(chunk_id, {})
            vectors.append(
                {
                    "id": chunk_id,
                    "vector": vector,
                    "chunk_id": chunk_id,
                    "repo_id": repo_id,
                    "file_path": meta.get("file_path", ""),
                    "start_line": meta.get("start_line", 0),
                    "end_line": meta.get("end_line", 0),
                    "language": meta.get("language", "unknown"),
                }
            )

        job.result = {"progress": 0.8, "message": "Upserting vectors"}
        db.commit()

        # Step 4 – Vector store upsert
        get_vector_store().upsert(vectors)

        job.status = "completed"
        job.result = {
            "progress": 1.0,
            "message": f"Indexed {len(file_tuples)} files, {len(all_chunks)} chunks",
        }
        db.commit()
        logger.info("Indexing job %s completed successfully", job_id)

    except Exception as exc:
        logger.error("Indexing job %s failed: %s", job_id, exc, exc_info=True)
        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.status = "failed"
                job.result = {"progress": 0.0, "message": str(exc)}
                db.commit()
        except Exception as inner_exc:
            logger.error("Could not update failed job status: %s", inner_exc)
    finally:
        db.close()
