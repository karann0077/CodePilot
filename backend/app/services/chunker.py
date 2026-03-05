import logging
import re
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import Chunk

logger = logging.getLogger(__name__)

_SLIDING_WINDOW_SIZE = 200
_SLIDING_WINDOW_OVERLAP = 50
_LARGE_FILE_THRESHOLD = 1000
# Average ~1.3 BPE tokens per whitespace-delimited word for typical source code
_TOKEN_MULTIPLIER = 1.3


def chunk_file(
    file_id: str,
    file_path: str,
    content: str,
    language: str,
    db_session: Session,
) -> list[dict]:
    """
    Split a file into logical chunks based on language, persist to DB.

    Returns list of dicts with {id, file_id, start_line, end_line,
    text, tokens, language}.
    """
    lines = content.splitlines()
    total_lines = len(lines)
    is_large = total_lines > _LARGE_FILE_THRESHOLD

    raw_chunks: list[tuple[int, int]] = _extract_chunks(lines, language)

    # Delete existing chunks for this file (re-index scenario)
    try:
        db_session.query(Chunk).filter(Chunk.file_id == file_id).delete()
        db_session.flush()
    except Exception as exc:
        logger.warning("Could not delete old chunks for file %s: %s", file_id, exc)
        db_session.rollback()

    results: list[dict] = []
    for start_line, end_line in raw_chunks:
        chunk_lines = lines[start_line:end_line]
        text = "\n".join(chunk_lines)
        if not text.strip():
            continue

        if is_large:
            header = f"# File: {file_path} (lines {start_line + 1}-{end_line})\n"
            text = header + text

        # 1.3x multiplier accounts for subword tokenisation overhead
        # (avg ~1.3 BPE tokens per whitespace-delimited word for code)
        tokens = int(len(text.split()) * _TOKEN_MULTIPLIER)

        chunk = Chunk(
            file_id=file_id,
            start_line=start_line + 1,  # 1-indexed
            end_line=end_line,
            text=text,
            tokens=tokens,
        )
        db_session.add(chunk)
        try:
            db_session.flush()
        except Exception as exc:
            logger.error("DB flush error for chunk in %s: %s", file_path, exc)
            db_session.rollback()
            continue

        results.append(
            {
                "id": chunk.id,
                "file_id": file_id,
                "file_path": file_path,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "text": text,
                "tokens": tokens,
                "language": language,
            }
        )

    try:
        db_session.commit()
    except Exception as exc:
        logger.error("DB commit error during chunking of %s: %s", file_path, exc)
        db_session.rollback()

    logger.debug(
        "Chunked %s (%s): %d chunks", file_path, language, len(results)
    )
    return results


def _extract_chunks(lines: list[str], language: str) -> list[tuple[int, int]]:
    """Return list of (start_line_0indexed, end_line_exclusive) pairs."""
    lang = language.lower()

    if lang == "python":
        return _python_chunks(lines)
    if lang in ("javascript", "typescript", "jsx", "tsx"):
        return _js_ts_chunks(lines)
    if lang == "java":
        return _java_chunks(lines)
    if lang == "go":
        return _go_chunks(lines)
    return _sliding_window_chunks(lines)


# -----------------------------------------------------------------------
# Language-specific splitters
# -----------------------------------------------------------------------

_PY_DEF_RE = re.compile(r"^(def |class )")
_PY_INDENT_RE = re.compile(r"^(\s*)")


def _python_chunks(lines: list[str]) -> list[tuple[int, int]]:
    starts: list[int] = [
        i for i, line in enumerate(lines) if _PY_DEF_RE.match(line)
    ]
    return _starts_to_ranges(starts, len(lines))


_JS_DEF_RE = re.compile(
    r"^(export\s+)?(default\s+)?(async\s+)?(function[\s*]|class )"
    r"|^(export\s+)?(const|let|var)\s+\w+\s*=\s*(async\s+)?[([]"
    r"|^\s*(async\s+)?function\s+\w+"
)


def _js_ts_chunks(lines: list[str]) -> list[tuple[int, int]]:
    starts: list[int] = [
        i for i, line in enumerate(lines) if _JS_DEF_RE.match(line)
    ]
    if not starts:
        return _sliding_window_chunks(lines)
    return _starts_to_ranges(starts, len(lines))


_JAVA_DEF_RE = re.compile(
    r"^\s*(public|private|protected|static|\s)*\s+"
    r"(class |interface |enum |[\w<>\[\]]+\s+\w+\s*\()"
)


def _java_chunks(lines: list[str]) -> list[tuple[int, int]]:
    starts: list[int] = [
        i for i, line in enumerate(lines) if _JAVA_DEF_RE.match(line)
    ]
    if not starts:
        return _sliding_window_chunks(lines)
    return _starts_to_ranges(starts, len(lines))


_GO_DEF_RE = re.compile(r"^func ")


def _go_chunks(lines: list[str]) -> list[tuple[int, int]]:
    starts: list[int] = [
        i for i, line in enumerate(lines) if _GO_DEF_RE.match(line)
    ]
    if not starts:
        return _sliding_window_chunks(lines)
    return _starts_to_ranges(starts, len(lines))


def _starts_to_ranges(
    starts: list[int], total: int
) -> list[tuple[int, int]]:
    """Convert list of start positions to (start, end) pairs."""
    if not starts:
        return [(0, total)]
    ranges: list[tuple[int, int]] = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else total
        ranges.append((start, end))
    return ranges


def _sliding_window_chunks(lines: list[str]) -> list[tuple[int, int]]:
    """Fallback: sliding window of fixed size with overlap."""
    total = len(lines)
    if total == 0:
        return []
    chunks: list[tuple[int, int]] = []
    start = 0
    while start < total:
        end = min(start + _SLIDING_WINDOW_SIZE, total)
        chunks.append((start, end))
        if end == total:
            break
        start += _SLIDING_WINDOW_SIZE - _SLIDING_WINDOW_OVERLAP
    return chunks
