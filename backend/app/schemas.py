from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Repo
# ---------------------------------------------------------------------------

class RepoConnect(BaseModel):
    name: str
    git_url: str
    default_branch: str = "main"


class RepoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    git_url: str
    local_path: Optional[str] = None
    default_branch: str
    created_at: datetime
    status: str = "connected"
    file_count: int = 0
    chunk_count: int = 0


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

class IndexStartRequest(BaseModel):
    repo_id: str


class IndexStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: float = 0.0
    message: str = ""


# ---------------------------------------------------------------------------
# Query / RAG
# ---------------------------------------------------------------------------

class ChunkInfo(BaseModel):
    id: str
    file_path: str
    start_line: int
    end_line: int
    text: str
    score: float


class Citation(BaseModel):
    file_path: str
    start_line: int
    end_line: int
    text: str
    score: float


class QueryRequest(BaseModel):
    repo_id: str
    question: str
    top_k: int = 8


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    cached: bool = False


# ---------------------------------------------------------------------------
# Diagnose
# ---------------------------------------------------------------------------

class Suspect(BaseModel):
    file_path: str
    start_line: int
    end_line: int
    probability: float
    explanation: str


class DiagnoseRequest(BaseModel):
    repo_id: str
    error_text: str
    stacktrace: str = ""


class DiagnoseResponse(BaseModel):
    suspects: list[Suspect]


# ---------------------------------------------------------------------------
# Patch
# ---------------------------------------------------------------------------

class Hunk(BaseModel):
    header: str
    lines: list[str]


class PatchRequest(BaseModel):
    repo_id: str
    issue_description: str
    file_path: Optional[str] = None


class PatchResponse(BaseModel):
    patch_id: str
    target_file: str
    hunks: list[Hunk]
    raw_diff: str
    explanation: str
    unit_test: str
    confidence: float


# ---------------------------------------------------------------------------
# Sandbox
# ---------------------------------------------------------------------------

class TestResult(BaseModel):
    name: str
    status: str  # passed | failed | error | skipped
    duration_ms: float = 0.0
    message: str = ""


class SandboxRunRequest(BaseModel):
    patch_id: str
    repo_id: str


class SandboxResultResponse(BaseModel):
    job_id: str
    status: str
    stdout: str = ""
    stderr: str = ""
    test_results: list[TestResult] = []
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# Doc Generation
# ---------------------------------------------------------------------------

class DocGenRequest(BaseModel):
    repo_id: str
    file_path: Optional[str] = None


class DocGenResponse(BaseModel):
    job_id: str
    status: str


class DocEntry(BaseModel):
    chunk_id: str
    file_path: str
    start_line: int
    end_line: int
    docstring: str
    example: str
    complexity: str


class DocGenResultResponse(BaseModel):
    job_id: str
    status: str
    doc_count: Optional[int] = None
    docs: Optional[list[DocEntry]] = None
    error: Optional[str] = None
