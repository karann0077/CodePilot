import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import Citation, QueryRequest, QueryResponse
from app.services import retriever
from app.services.llm_orchestrator import get_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/query", tags=["query"])


@router.post("/", response_model=QueryResponse)
async def query_repo(
    body: QueryRequest, db: Session = Depends(get_db)
) -> QueryResponse:
    """Answer a question about a repository using RAG."""
    if not body.question.strip():
        raise HTTPException(status_code=422, detail="Question cannot be empty")

    try:
        chunks = retriever.retrieve(
            query=body.question,
            repo_id=body.repo_id,
            top_k=body.top_k,
            db_session=db,
        )
    except Exception as exc:
        logger.error("Retrieval failed for repo %s: %s", body.repo_id, exc)
        raise HTTPException(status_code=500, detail="Retrieval error") from exc

    if not chunks:
        return QueryResponse(
            answer="No relevant code found for the given question.",
            citations=[],
            cached=False,
        )

    orchestrator = get_orchestrator()
    system, user_prompt = orchestrator.assemble_prompt(chunks, body.question, task="query")

    try:
        answer = await orchestrator.generate(
            prompt=user_prompt,
            system=system,
            repo_id=body.repo_id,
        )
    except Exception as exc:
        logger.error("LLM generation failed: %s", exc)
        raise HTTPException(status_code=500, detail="LLM error") from exc

    citations = [
        Citation(
            file_path=c["file_path"],
            start_line=c["start_line"],
            end_line=c["end_line"],
            text=c["text"],
            score=c["score"],
        )
        for c in chunks
    ]

    return QueryResponse(answer=answer, citations=citations, cached=False)
