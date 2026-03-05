import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models import Job
from app.schemas import DocGenRequest, DocGenResponse

logger = logging.getLogger(__name__)

# Note: This file is docs.py but the router prefix is /docs_gen to avoid
# conflict with FastAPI's built-in /docs endpoint.
router = APIRouter(prefix="/docs_gen", tags=["docs"])


@router.post("/generate", response_model=DocGenResponse, status_code=202)
def generate_docs(
    body: DocGenRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> DocGenResponse:
    """Start a documentation generation job for a repository or specific file."""
    job = Job(
        type="doc_gen",
        status="pending",
        repo_id=body.repo_id,
        payload={
            "repo_id": body.repo_id,
            "file_path": body.file_path,
        },
    )
    db.add(job)
    try:
        db.commit()
        db.refresh(job)
    except Exception as exc:
        db.rollback()
        logger.error("Failed to create doc_gen job: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create job") from exc

    background_tasks.add_task(
        _run_doc_generation, job.id, body.repo_id, body.file_path
    )
    return DocGenResponse(job_id=job.id, status=job.status)


def _run_doc_generation(
    job_id: str, repo_id: str, file_path: str | None
) -> None:
    """Background task: generate documentation and persist results."""
    import asyncio

    from app.services.doc_generator import get_doc_generator

    db: Session = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.error("Doc gen job %s not found", job_id)
            return

        job.status = "running"
        db.commit()

        doc_generator = get_doc_generator()

        # Run the async generator in a new event loop
        loop = asyncio.new_event_loop()
        try:
            docs = loop.run_until_complete(
                doc_generator.generate_for_repo(
                    repo_id=repo_id,
                    file_path=file_path,
                    db_session=db,
                )
            )
        finally:
            loop.close()

        job.status = "completed"
        job.result = {"doc_count": len(docs), "docs": docs}
        db.commit()
        logger.info(
            "Doc gen job %s completed: %d documents generated", job_id, len(docs)
        )

    except Exception as exc:
        logger.error("Doc gen job %s failed: %s", job_id, exc, exc_info=True)
        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.status = "failed"
                job.result = {"error": str(exc)}
                db.commit()
        except Exception as inner_exc:
            logger.error("Could not update failed doc gen job: %s", inner_exc)
    finally:
        db.close()
