import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import DiagnoseRequest, DiagnoseResponse, Suspect
from app.services import retriever
from app.services.llm_orchestrator import get_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnose", tags=["diagnose"])


@router.post("/", response_model=DiagnoseResponse)
async def diagnose(
    body: DiagnoseRequest, db: Session = Depends(get_db)
) -> DiagnoseResponse:
    """Diagnose an error by finding suspect code locations."""
    combined_query = body.error_text
    if body.stacktrace:
        combined_query = f"{body.error_text}\n\n{body.stacktrace}"

    if not combined_query.strip():
        raise HTTPException(status_code=422, detail="error_text cannot be empty")

    try:
        chunks = retriever.retrieve(
            query=combined_query,
            repo_id=body.repo_id,
            top_k=10,
            db_session=db,
        )
    except Exception as exc:
        logger.error("Retrieval failed during diagnose for repo %s: %s", body.repo_id, exc)
        raise HTTPException(status_code=500, detail="Retrieval error") from exc

    if not chunks:
        return DiagnoseResponse(suspects=[])

    orchestrator = get_orchestrator()
    system = (
        "You are a debugging assistant. Analyse the provided error and code snippets. "
        "For each suspect code location output a line in this exact format:\n"
        "SUSPECT: <file_path>:<start_line>-<end_line> PROBABILITY:<0.0-1.0> REASON:<brief explanation>\n"
        "List the most likely suspects first."
    )
    _, user_prompt = orchestrator.assemble_prompt(chunks, combined_query, task="diagnose")

    try:
        answer = await orchestrator.generate(
            prompt=user_prompt,
            system=system,
            repo_id=body.repo_id,
        )
    except Exception as exc:
        logger.error("LLM diagnosis failed: %s", exc)
        raise HTTPException(status_code=500, detail="LLM error") from exc

    suspects = _parse_suspects(answer, chunks)
    return DiagnoseResponse(suspects=suspects)


def _parse_suspects(llm_output: str, chunks: list[dict]) -> list[Suspect]:
    """
    Parse LLM output for SUSPECT lines.

    Falls back to top-scored chunks if no structured output found.
    """
    import re

    suspects: list[Suspect] = []
    pattern = re.compile(
        r"SUSPECT:\s*(\S+):(\d+)-(\d+)\s+PROBABILITY:([\d.]+)\s+REASON:(.*)",
        re.IGNORECASE,
    )
    for line in llm_output.splitlines():
        m = pattern.search(line)
        if m:
            try:
                suspects.append(
                    Suspect(
                        file_path=m.group(1),
                        start_line=int(m.group(2)),
                        end_line=int(m.group(3)),
                        probability=min(1.0, max(0.0, float(m.group(4)))),
                        explanation=m.group(5).strip(),
                    )
                )
            except (ValueError, IndexError) as exc:
                logger.warning("Could not parse SUSPECT line: %s (%s)", line, exc)

    # Fallback: convert top chunks to suspects
    if not suspects:
        for chunk in chunks[:5]:
            suspects.append(
                Suspect(
                    file_path=chunk["file_path"],
                    start_line=chunk["start_line"],
                    end_line=chunk["end_line"],
                    probability=round(min(1.0, chunk["score"]), 3),
                    explanation="Identified by semantic similarity to error",
                )
            )
    return suspects
