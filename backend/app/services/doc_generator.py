import logging
import re

from sqlalchemy.orm import Session

from app.models import Chunk, File

logger = logging.getLogger(__name__)


class DocGenerator:
    """Generates documentation for code chunks using the LLM orchestrator."""

    async def generate_for_repo(
        self,
        repo_id: str,
        file_path: str | None = None,
        db_session: Session | None = None,
    ) -> list[dict]:
        """
        Generate docstrings and notes for code-bearing chunks in a repo.

        Returns list of {chunk_id, file_path, start_line, end_line,
                          docstring, example, complexity}.
        """
        from app.services.llm_orchestrator import get_orchestrator

        orchestrator = get_orchestrator()

        if db_session is None:
            logger.warning("No db_session provided; returning empty docs")
            return []

        query = (
            db_session.query(Chunk, File.path.label("file_path"), File.language.label("language"))
            .join(File, Chunk.file_id == File.id)
            .filter(File.repo_id == repo_id)
        )
        if file_path:
            query = query.filter(File.path == file_path)

        rows = query.all()

        _CODE_INDICATORS = ("def ", "class ", "function ", "func ", "=>")
        results: list[dict] = []

        for chunk, fp, lang in rows:
            text = chunk.text or ""
            if not any(indicator in text for indicator in _CODE_INDICATORS):
                continue

            chunk_language = lang or "unknown"
            prompt = (
                f"Generate a docstring, example usage, and complexity notes "
                f"for this {chunk_language} code:\n\n{text}"
            )
            system = (
                "You are a documentation expert. "
                "Provide concise, accurate documentation. "
                "Format your response as:\n"
                "Docstring: <docstring>\n"
                "Example:\n```\n<usage example>\n```\n"
                "Complexity: <complexity notes>"
            )

            try:
                response = await orchestrator.generate(
                    prompt=prompt,
                    system=system,
                    repo_id=repo_id,
                )
                docstring, example, complexity = self._parse_response(response)
            except Exception as exc:
                logger.error("Doc generation failed for chunk %s: %s", chunk.id, exc)
                docstring = example = complexity = ""

            results.append(
                {
                    "chunk_id": chunk.id,
                    "file_path": fp,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "docstring": docstring,
                    "example": example,
                    "complexity": complexity,
                }
            )

        logger.info(
            "Generated docs for %d chunks in repo %s", len(results), repo_id
        )
        return results

    def _parse_response(self, response: str) -> tuple[str, str, str]:
        """
        Parse LLM response into (docstring, example, complexity).

        Handles both structured and free-form responses.
        """
        docstring = ""
        example = ""
        complexity = ""

        # Try structured format first
        doc_match = re.search(r"Docstring:\s*(.*?)(?=Example:|Complexity:|$)", response, re.DOTALL | re.IGNORECASE)
        if doc_match:
            docstring = doc_match.group(1).strip()

        ex_match = re.search(r"Example:\s*```(?:\w+)?\n?(.*?)```", response, re.DOTALL | re.IGNORECASE)
        if not ex_match:
            ex_match = re.search(r"Example:\s*(.*?)(?=Complexity:|$)", response, re.DOTALL | re.IGNORECASE)
        if ex_match:
            example = ex_match.group(1).strip()

        comp_match = re.search(r"Complexity:\s*(.*?)$", response, re.DOTALL | re.IGNORECASE)
        if comp_match:
            complexity = comp_match.group(1).strip()

        # Fallback: use paragraphs
        if not docstring:
            paragraphs = [p.strip() for p in response.split("\n\n") if p.strip()]
            if paragraphs:
                docstring = paragraphs[0]
            if len(paragraphs) > 1:
                complexity = paragraphs[-1]

        return docstring, example, complexity


_doc_generator_instance: DocGenerator | None = None


def get_doc_generator() -> DocGenerator:
    """Return the singleton DocGenerator instance."""
    global _doc_generator_instance
    if _doc_generator_instance is None:
        _doc_generator_instance = DocGenerator()
    return _doc_generator_instance
