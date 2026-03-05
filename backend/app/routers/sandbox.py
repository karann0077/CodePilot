import logging
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models import Job, Repo
from app.schemas import SandboxResultResponse, SandboxRunRequest, TestResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sandbox", tags=["sandbox"])

_REPOS_BASE_DIR = os.environ.get("REPOS_BASE_DIR", "repos")


@router.post("/run")
def run_sandbox(
    body: SandboxRunRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    """Run a patch in a sandboxed environment."""
    repo = db.query(Repo).filter(Repo.id == body.repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    # Look up patch diff from prior patch job (stored as result.raw_diff)
    patch_diff = ""
    if body.patch_id:
        patch_job = (
            db.query(Job)
            .filter(Job.type == "patch", Job.id == body.patch_id)
            .first()
        )
        if patch_job and patch_job.result:
            patch_diff = patch_job.result.get("raw_diff", "")

    job = Job(
        type="sandbox",
        status="pending",
        repo_id=body.repo_id,
        payload={"patch_id": body.patch_id, "repo_id": body.repo_id},
    )
    db.add(job)
    try:
        db.commit()
        db.refresh(job)
    except Exception as exc:
        db.rollback()
        logger.error("Failed to create sandbox job: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create sandbox job") from exc

    repo_path = os.path.join(_REPOS_BASE_DIR, body.repo_id)
    background_tasks.add_task(
        _run_sandbox_task, job.id, repo_path, patch_diff
    )
    return {"job_id": job.id}


@router.get("/result/{job_id}", response_model=SandboxResultResponse)
def get_sandbox_result(
    job_id: str, db: Session = Depends(get_db)
) -> SandboxResultResponse:
    """Get the result of a sandbox run."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    result = job.result or {}
    test_result_dicts: list[dict] = result.get("test_results", [])
    test_results = [
        TestResult(
            name=t.get("name", ""),
            status=t.get("status", "unknown"),
            duration_ms=t.get("duration_ms", 0.0),
            message=t.get("message", ""),
        )
        for t in test_result_dicts
    ]

    confidence = result.get("confidence", 0.0)

    return SandboxResultResponse(
        job_id=job.id,
        status=job.status,
        stdout=result.get("stdout", ""),
        stderr=result.get("stderr", ""),
        test_results=test_results,
        confidence=confidence,
    )


def _run_sandbox_task(job_id: str, repo_path: str, patch_diff: str) -> None:
    """Background task: run the sandbox and persist results."""
    from app.services.sandbox_runner import get_sandbox_runner
    from app.services.verifier import get_verifier

    db: Session = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.error("Sandbox job %s not found", job_id)
            return

        job.status = "running"
        db.commit()

        runner = get_sandbox_runner()
        sandbox_result = runner.run(repo_path, patch_diff, job_id)

        verifier = get_verifier()
        verification = verifier.score(sandbox_result, repo_path)
        confidence = verification["score"] / 100.0

        job.status = "completed"
        job.result = {**sandbox_result, "confidence": confidence}
        db.commit()
        logger.info("Sandbox job %s completed (confidence=%.2f)", job_id, confidence)

    except Exception as exc:
        logger.error("Sandbox job %s failed: %s", job_id, exc, exc_info=True)
        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.status = "failed"
                job.result = {"stdout": "", "stderr": str(exc), "test_results": [], "confidence": 0.0}
                db.commit()
        except Exception as inner_exc:
            logger.error("Could not update failed sandbox job: %s", inner_exc)
    finally:
        db.close()
