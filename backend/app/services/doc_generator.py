import logging
import re

from sqlalchemy.orm import Session

from app.models import Chunk, File
from app.services.prompt_manager import get_prompt_manager

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
            system, prompt = get_prompt_manager().render(
                "docs",
                language=chunk_language,
                code=text,
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

        Handles both structured and markdown-heavy responses.
        """

        def _extract_section(text: str, labels: list[str], stop_labels: list[str]) -> str:
            label_pattern = "|".join(re.escape(label) for label in labels)
            stop_pattern = "|".join(re.escape(label) for label in stop_labels)

            start_re = re.compile(
                rf"(?:^|\n)\s*(?:[#>*-]\s*)?(?:\*\*)?(?:{label_pattern})(?:\*\*)?\s*:?\s*",
                re.IGNORECASE,
            )
            start_match = start_re.search(text)
            if not start_match:
                return ""

            remainder = text[start_match.end():]
            if stop_pattern:
                stop_re = re.compile(
                    rf"(?:^|\n)\s*(?:[#>*-]\s*)?(?:\*\*)?(?:{stop_pattern})(?:\*\*)?\s*:?\s*",
                    re.IGNORECASE,
                )
                stop_match = stop_re.search(remainder)
                if stop_match:
                    return remainder[: stop_match.start()].strip()
            return remainder.strip()

        def _strip_markdown(text: str) -> str:
            cleaned = text.strip()
            cleaned = re.sub(r"^```[\w-]*\n", "", cleaned)
            cleaned = re.sub(r"\n```$", "", cleaned)
            cleaned = re.sub(r"^`{1,3}|`{1,3}$", "", cleaned)
            cleaned = cleaned.replace("**", "")
            cleaned = cleaned.strip()
            return cleaned

        raw = response.replace("\r\n", "\n").strip()

        docstring = _extract_section(
            raw,
            labels=["Docstring", "Documentation", "Summary"],
            stop_labels=["Example", "Usage", "Complexity", "Time Complexity", "Space Complexity"],
        )
        example = _extract_section(
            raw,
            labels=["Example", "Usage"],
            stop_labels=["Complexity", "Time Complexity", "Space Complexity", "Notes"],
        )
        complexity = _extract_section(
            raw,
            labels=["Complexity", "Time Complexity", "Space Complexity"],
            stop_labels=[],
        )

        if not docstring:
            paragraphs = [p.strip() for p in raw.split("\n\n") if p.strip()]
            if paragraphs:
                docstring = paragraphs[0]
            if len(paragraphs) > 1 and not complexity:
                complexity = paragraphs[-1]

        docstring = _strip_markdown(docstring)
        example = _strip_markdown(example)
        complexity = _strip_markdown(complexity)

        if example.startswith("python\n") or example.startswith("javascript\n"):
            example = example.split("\n", 1)[1].strip() if "\n" in example else ""

        return docstring, example, complexity


_doc_generator_instance: DocGenerator | None = None


def get_doc_generator() -> DocGenerator:
    """Return the singleton DocGenerator instance."""
    global _doc_generator_instance
    if _doc_generator_instance is None:
        _doc_generator_instance = DocGenerator()
    return _doc_generator_instance
