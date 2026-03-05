import hashlib
import logging
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import File
from app.utils.language_detect import detect_language, is_binary

logger = logging.getLogger(__name__)

_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".tox", ".venv", "venv", ".env"}
_SKIP_EXTENSIONS = {
    ".pyc", ".class", ".jar", ".zip", ".tar", ".gz",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf",
    ".exe", ".dll", ".so", ".dylib", ".whl", ".egg",
    ".mp3", ".mp4", ".avi", ".mov", ".wav", ".ogg",
    ".ttf", ".woff", ".woff2", ".eot",
    ".min.js",
}
_REPOS_BASE_DIR = os.environ.get("REPOS_BASE_DIR", "repos")


def ingest_repo(
    repo_id: str, git_url: str, db_session: Session
) -> list[tuple[str, str, str, str]]:
    """
    Clone (or extract) a repository and upsert File records.

    Returns list of (file_id, file_path, content, language) tuples.
    """
    repo_dir = Path(_REPOS_BASE_DIR) / repo_id
    repo_dir.mkdir(parents=True, exist_ok=True)

    if git_url.endswith(".zip"):
        _extract_zip(git_url, repo_dir)
    else:
        _clone_repo(git_url, repo_dir)

    return _walk_and_upsert(repo_id, repo_dir, db_session)


def _clone_repo(git_url: str, target_dir: Path) -> None:
    """Clone a git repository into target_dir."""
    if (target_dir / ".git").exists():
        logger.info("Repo already cloned at %s; pulling latest", target_dir)
        try:
            subprocess.run(
                ["git", "-C", str(target_dir), "pull", "--ff-only"],
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
        except subprocess.TimeoutExpired:
            logger.warning("git pull timed out for %s", target_dir)
        return

    logger.info("Cloning %s -> %s", git_url, target_dir)
    result = subprocess.run(
        ["git", "clone", "--depth=1", git_url, str(target_dir)],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git clone failed for {git_url}: {result.stderr.strip()}"
        )
    logger.info("Clone complete: %s", target_dir)


def _extract_zip(zip_path: str, target_dir: Path) -> None:
    """Extract a zip archive into target_dir."""
    logger.info("Extracting zip %s -> %s", zip_path, target_dir)
    local_zip = Path(zip_path)
    if not local_zip.exists():
        raise FileNotFoundError(f"Zip file not found: {zip_path}")
    with zipfile.ZipFile(local_zip, "r") as zf:
        zf.extractall(target_dir)
    logger.info("Extraction complete: %s", target_dir)


def _walk_and_upsert(
    repo_id: str, repo_dir: Path, db_session: Session
) -> list[tuple[str, str, str, str]]:
    """Walk the repo directory and upsert File records in the DB."""
    results: list[tuple[str, str, str, str]] = []

    for root, dirs, files in os.walk(repo_dir):
        # Prune skip dirs in-place to avoid descending into them
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]

        for filename in files:
            abs_path = Path(root) / filename
            rel_path = str(abs_path.relative_to(repo_dir))

            # Skip by extension
            suffix = abs_path.suffix.lower()
            if suffix in _SKIP_EXTENSIONS:
                continue
            # Handle compound extensions like .min.js
            if any(rel_path.endswith(ext) for ext in _SKIP_EXTENSIONS):
                continue

            # Skip binary files
            if is_binary(str(abs_path)):
                continue

            try:
                content = abs_path.read_text(encoding="utf-8", errors="replace")
            except (OSError, IOError) as exc:
                logger.warning("Could not read %s: %s", abs_path, exc)
                continue

            language = detect_language(str(abs_path))
            checksum = hashlib.sha256(content.encode()).hexdigest()

            file_record = (
                db_session.query(File)
                .filter(File.repo_id == repo_id, File.path == rel_path)
                .first()
            )
            if file_record:
                file_record.language = language
                file_record.checksum = checksum
            else:
                file_record = File(
                    repo_id=repo_id,
                    path=rel_path,
                    language=language,
                    checksum=checksum,
                )
                db_session.add(file_record)

            try:
                db_session.flush()
            except Exception as exc:
                logger.error("DB flush error for %s: %s", rel_path, exc)
                db_session.rollback()
                continue

            results.append((file_record.id, rel_path, content, language))

    try:
        db_session.commit()
    except Exception as exc:
        logger.error("DB commit error during ingestion: %s", exc)
        db_session.rollback()

    logger.info("Ingestion complete: %d files for repo %s", len(results), repo_id)
    return results
