import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Repo
from app.schemas import Hunk, PatchRequest, PatchResponse
from app.services import retriever
from app.services.llm_orchestrator import get_orchestrator
from app.services.patch_engine import get_patch_engine

logger = logging.getLogger(__name__)

# Confidence scoring weights
_VALID_DIFF_BASE = 0.5   # base score when diff passes validation
_INVALID_DIFF_BASE = 0.1  # base score when diff is malformed
_RETRIEVAL_SCORE_WEIGHT = 0.5  # contribution of avg retrieval score to confidence

router = APIRouter(prefix="/patch", tags=["patch"])


@router.post("/propose", response_model=PatchResponse)
async def propose_patch(
    body: PatchRequest, db: Session = Depends(get_db)
) -> PatchResponse:
    """Generate a patch proposal for a given issue description."""
    if not body.issue_description.strip():
        raise HTTPException(status_code=422, detail="issue_description cannot be empty")

    repo = db.query(Repo).filter(Repo.id == body.repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    query = body.issue_description
    if body.file_path:
        query = f"file:{body.file_path} {query}"

    try:
        chunks = retriever.retrieve(
            query=query,
            repo_id=body.repo_id,
            top_k=8,
            db_session=db,
        )
    except Exception as exc:
        logger.error("Retrieval failed for patch proposal: %s", exc)
        raise HTTPException(status_code=500, detail="Retrieval error") from exc

    patch_engine = get_patch_engine()
    orchestrator = get_orchestrator()

    patch_prompt = patch_engine.create_patch_prompt(chunks, body.issue_description)
    system = (
        "You are a code repair expert. "
        "Produce a minimal, correct unified diff that fixes the described issue. "
        "Always include --- a/ and +++ b/ headers, and @@ hunk markers."
    )

    try:
        llm_output = await orchestrator.generate(
            prompt=patch_prompt,
            system=system,
            repo_id=body.repo_id,
        )
    except Exception as exc:
        logger.error("LLM patch generation failed: %s", exc)
        raise HTTPException(status_code=500, detail="LLM error") from exc

    parsed = patch_engine.parse_llm_output(llm_output)

    target_file = parsed.get("target_file") or (
        body.file_path or (chunks[0]["file_path"] if chunks else "unknown")
    )
    raw_hunks = parsed.get("hunks", [])
    hunks = [Hunk(header=h["header"], lines=h["lines"]) for h in raw_hunks]
    raw_diff = parsed.get("raw_diff", "")

    # Estimate confidence based on diff validity and chunk scores
    is_valid = patch_engine.validate_diff(raw_diff)
    avg_score = (
        sum(c["score"] for c in chunks) / len(chunks) if chunks else 0.0
    )
    confidence = round(
        min(1.0, (_VALID_DIFF_BASE if is_valid else _INVALID_DIFF_BASE) + avg_score * _RETRIEVAL_SCORE_WEIGHT),
        3,
    )

    return PatchResponse(
        patch_id=str(uuid4()),
        target_file=target_file,
        hunks=hunks,
        raw_diff=raw_diff,
        explanation=parsed.get("explanation", ""),
        unit_test=parsed.get("unit_test", ""),
        confidence=confidence,
    )
