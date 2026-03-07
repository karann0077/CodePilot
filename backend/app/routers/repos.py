import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Repo
from app.schemas import RepoConnect, RepoResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/repos", tags=["repos"])


def _database_unavailable() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail="Database unavailable. Please verify backend database configuration.",
    )


@router.post("/connect", response_model=RepoResponse, status_code=201)
def connect_repo(body: RepoConnect, db: Session = Depends(get_db)) -> RepoResponse:
    """Register a new repository."""
    try:
        existing = db.query(Repo).filter(Repo.git_url == body.git_url).first()
        if existing:
            raise HTTPException(status_code=409, detail="Repository already registered")

        repo = Repo(
            name=body.name,
            git_url=body.git_url,
            default_branch=body.default_branch,
        )
        db.add(repo)
        db.commit()
        db.refresh(repo)
        return RepoResponse.model_validate(repo)
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Repository creation failed")
        raise _database_unavailable() from exc


@router.get("", response_model=list[RepoResponse], include_in_schema=False)
@router.get("/", response_model=list[RepoResponse])
def list_repos(db: Session = Depends(get_db)) -> list[RepoResponse]:
    """List all registered repositories."""
    try:
        repos = db.query(Repo).order_by(Repo.created_at.desc()).all()
        return [RepoResponse.model_validate(r) for r in repos]
    except Exception as exc:
        logger.exception("Repository list failed")
        raise _database_unavailable() from exc


@router.delete("/{repo_id}")
def delete_repo(repo_id: str, db: Session = Depends(get_db)) -> dict:
    """Delete a repository and all related data."""
    try:
        repo = db.query(Repo).filter(Repo.id == repo_id).first()
        if not repo:
            raise HTTPException(status_code=404, detail="Repository not found")

        # Cascade delete handles files/chunks via relationship config.
        # Also remove any vector store data.
        from app.services.vector_store import get_vector_store

        try:
            get_vector_store().delete_repo(repo_id)
        except Exception as exc:
            logger.warning("Could not delete vectors for repo %s: %s", repo_id, exc)

        db.delete(repo)
        db.commit()
        return {"deleted": repo_id}
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Repository delete failed for %s", repo_id)
        raise _database_unavailable() from exc
