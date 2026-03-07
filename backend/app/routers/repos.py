import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Repo
from app.schemas import RepoConnect, RepoResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/repos", tags=["repos"])


@router.post("/connect", response_model=RepoResponse, status_code=201)
def connect_repo(body: RepoConnect, db: Session = Depends(get_db)) -> RepoResponse:
    """Register a new repository."""
    try:
        existing = db.query(Repo).filter(Repo.git_url == body.git_url).first()
    except SQLAlchemyError as exc:
        logger.error("Database error while checking repo existence: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Database unavailable. Please verify backend database configuration.",
        ) from exc
    if existing:
        raise HTTPException(status_code=409, detail="Repository already registered")

    repo = Repo(
        name=body.name,
        git_url=body.git_url,
        default_branch=body.default_branch,
    )
    db.add(repo)
    try:
        db.commit()
        db.refresh(repo)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Database error while creating repo: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Database unavailable. Please verify backend database configuration.",
        ) from exc
    except Exception as exc:
        db.rollback()
        logger.error("Failed to create repo: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create repository") from exc

    return RepoResponse.model_validate(repo)


@router.get("", response_model=list[RepoResponse], include_in_schema=False)
@router.get("/", response_model=list[RepoResponse])
def list_repos(db: Session = Depends(get_db)) -> list[RepoResponse]:
    """List all registered repositories."""
    try:
        repos = db.query(Repo).order_by(Repo.created_at.desc()).all()
    except SQLAlchemyError as exc:
        logger.error("Database error while listing repos: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Database unavailable. Please verify backend database configuration.",
        ) from exc
    return [RepoResponse.model_validate(r) for r in repos]


@router.delete("/{repo_id}")
def delete_repo(repo_id: str, db: Session = Depends(get_db)) -> dict:
    """Delete a repository and all related data."""
    try:
        repo = db.query(Repo).filter(Repo.id == repo_id).first()
    except SQLAlchemyError as exc:
        logger.error("Database error while loading repo %s: %s", repo_id, exc)
        raise HTTPException(
            status_code=503,
            detail="Database unavailable. Please verify backend database configuration.",
        ) from exc
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    try:
        # Cascade delete handles files/chunks via relationship config.
        # Also remove any vector store data.
        from app.services.vector_store import get_vector_store
        try:
            get_vector_store().delete_repo(repo_id)
        except Exception as exc:
            logger.warning("Could not delete vectors for repo %s: %s", repo_id, exc)

        db.delete(repo)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Database error while deleting repo %s: %s", repo_id, exc)
        raise HTTPException(
            status_code=503,
            detail="Database unavailable. Please verify backend database configuration.",
        ) from exc
    except Exception as exc:
        db.rollback()
        logger.error("Failed to delete repo %s: %s", repo_id, exc)
        raise HTTPException(status_code=500, detail="Failed to delete repository") from exc

    return {"deleted": repo_id}
