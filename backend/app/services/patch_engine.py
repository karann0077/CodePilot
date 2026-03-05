import logging
import re

from app.utils.diff_utils import (
    extract_target_file,
    parse_unified_diff,
    validate_diff,
)

logger = logging.getLogger(__name__)


class PatchEngine:
    """Parses, validates, and prepares unified-diff patches from LLM output."""

    def parse_llm_output(self, text: str) -> dict:
        """
        Extract patch components from raw LLM output.

        Returns a dict with keys: target_file, hunks, raw_diff,
        explanation, unit_test.
        """
        raw_diff = self._extract_diff_block(text)
        target_file = ""
        hunks: list[dict] = []

        if raw_diff and validate_diff(raw_diff):
            target_file = extract_target_file(raw_diff) or ""
            parsed_hunks = parse_unified_diff(raw_diff)
            hunks = [
                {"header": h["header"], "lines": h["lines"]}
                for h in parsed_hunks
            ]
        elif raw_diff:
            # Best-effort: wrap non-standard diff in a synthetic header
            target_file = self._guess_filename(text)
            raw_diff = self._make_best_effort_diff(raw_diff, target_file)
            if validate_diff(raw_diff):
                parsed_hunks = parse_unified_diff(raw_diff)
                hunks = [
                    {"header": h["header"], "lines": h["lines"]}
                    for h in parsed_hunks
                ]

        explanation = self._extract_explanation(text, raw_diff or "")
        unit_test = self._extract_unit_test(text)

        return {
            "target_file": target_file,
            "hunks": hunks,
            "raw_diff": raw_diff or "",
            "explanation": explanation,
            "unit_test": unit_test,
        }

    def validate_diff(self, diff: str) -> bool:
        """Return True if diff is a valid unified diff."""
        return validate_diff(diff)

    def create_patch_prompt(
        self, chunks: list[dict], issue_description: str
    ) -> str:
        """Build a prompt requesting a unified diff for the described issue."""
        snippets: list[str] = []
        for chunk in chunks:
            lang = chunk.get("language", "")
            fp = chunk.get("file_path", "unknown")
            sl = chunk.get("start_line", 0)
            el = chunk.get("end_line", 0)
            text = chunk.get("text", "")
            snippets.append(
                f"[File: {fp} L{sl}-{el}]\n```{lang}\n{text}\n```"
            )

        context = "\n\n".join(snippets)
        return (
            f"You are a code repair assistant.\n\n"
            f"Issue:\n{issue_description}\n\n"
            f"Relevant code:\n\n{context}\n\n"
            f"Produce a minimal unified diff (--- a/... +++ b/... @@ ... @@) "
            f"that fixes the issue. Include:\n"
            f"1. The unified diff block.\n"
            f"2. A brief explanation of the change.\n"
            f"3. A Python unit test for the fix inside a ```python``` block.\n"
            f"Output only the diff, explanation, and test — no other text."
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_diff_block(self, text: str) -> str | None:
        """Extract a unified diff from ```diff ... ``` or raw diff lines."""
        # Try fenced block first
        fenced = re.search(r"```(?:diff)?\n(.*?)```", text, re.DOTALL)
        if fenced:
            candidate = fenced.group(1)
            if validate_diff(candidate):
                return candidate.strip()

        # Try raw unified diff lines
        lines = text.splitlines()
        diff_lines: list[str] = []
        in_diff = False
        for line in lines:
            if line.startswith("--- ") or line.startswith("+++ "):
                in_diff = True
            if in_diff:
                if line.startswith(("--- ", "+++ ", "@@ ", "+", "-", " ")):
                    diff_lines.append(line)
                elif diff_lines:
                    break  # End of diff block

        if diff_lines:
            candidate = "\n".join(diff_lines)
            if validate_diff(candidate):
                return candidate

        return fenced.group(1).strip() if fenced else None

    def _guess_filename(self, text: str) -> str:
        """Heuristically guess the target filename from LLM output."""
        match = re.search(r"(?:file[:\s]+|in\s+)([`\"]?)(\S+\.(?:py|js|ts|java|go|rs))\1", text, re.IGNORECASE)
        if match:
            return match.group(2)
        return "unknown_file"

    def _make_best_effort_diff(self, code_block: str, filename: str) -> str:
        """Wrap a raw code block in a synthetic diff header."""
        lines = [f"+{l}" for l in code_block.splitlines()]
        count = len(lines)
        return (
            f"--- a/{filename}\n"
            f"+++ b/{filename}\n"
            f"@@ -0,0 +1,{count} @@\n"
            + "\n".join(lines)
        )

    def _extract_explanation(self, text: str, diff: str) -> str:
        """Extract explanation text from LLM output (text before or after diff)."""
        clean = text
        if diff:
            clean = clean.replace(diff, "")
        # Remove code fences
        clean = re.sub(r"```.*?```", "", clean, flags=re.DOTALL)
        paragraphs = [p.strip() for p in clean.split("\n\n") if p.strip()]
        return paragraphs[0] if paragraphs else ""

    def _extract_unit_test(self, text: str) -> str:
        """Extract Python unit test from ```python ... ``` block."""
        for match in re.finditer(r"```python\n(.*?)```", text, re.DOTALL):
            block = match.group(1)
            if "def test_" in block:
                return block.strip()
        return ""


_patch_engine_instance: PatchEngine | None = None


def get_patch_engine() -> PatchEngine:
    """Return the singleton PatchEngine instance."""
    global _patch_engine_instance
    if _patch_engine_instance is None:
        _patch_engine_instance = PatchEngine()
    return _patch_engine_instance
