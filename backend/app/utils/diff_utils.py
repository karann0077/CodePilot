import difflib
import logging
import re

logger = logging.getLogger(__name__)


def parse_unified_diff(diff_text: str) -> list[dict]:
    """Parse a unified diff text into a list of hunk dictionaries."""
    hunks: list[dict] = []
    current_old_file: str = ""
    current_new_file: str = ""
    current_hunk: dict | None = None

    for line in diff_text.splitlines():
        if line.startswith("--- "):
            current_old_file = _strip_diff_prefix(line[4:].strip())
        elif line.startswith("+++ "):
            current_new_file = _strip_diff_prefix(line[4:].strip())
        elif line.startswith("@@ "):
            if current_hunk is not None:
                hunks.append(current_hunk)
            match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if match:
                old_start = int(match.group(1))
                old_count = int(match.group(2)) if match.group(2) is not None else 1
                new_start = int(match.group(3))
                new_count = int(match.group(4)) if match.group(4) is not None else 1
            else:
                old_start = old_count = new_start = new_count = 0
            current_hunk = {
                "old_file": current_old_file,
                "new_file": current_new_file,
                "header": line,
                "old_start": old_start,
                "old_count": old_count,
                "new_start": new_start,
                "new_count": new_count,
                "lines": [],
            }
        elif current_hunk is not None and (
            line.startswith("+")
            or line.startswith("-")
            or line.startswith(" ")
            or line == ""
        ):
            current_hunk["lines"].append(line)

    if current_hunk is not None:
        hunks.append(current_hunk)

    return hunks


def validate_diff(diff_text: str) -> bool:
    """Validate that diff_text is a well-formed unified diff."""
    if not diff_text or not diff_text.strip():
        return False
    has_old = any(line.startswith("--- ") for line in diff_text.splitlines())
    has_new = any(line.startswith("+++ ") for line in diff_text.splitlines())
    has_hunk = any(line.startswith("@@ ") for line in diff_text.splitlines())
    return has_old and has_new and has_hunk


def extract_target_file(diff_text: str) -> str | None:
    """Extract the target file name from a unified diff."""
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            return _strip_diff_prefix(path)
    return None


def apply_diff(original: str, diff_text: str) -> str:
    """Apply a unified diff to original content and return modified content."""
    hunks = parse_unified_diff(diff_text)
    if not hunks:
        logger.warning("No hunks found in diff; returning original content unchanged")
        return original

    lines = original.splitlines(keepends=True)
    # Ensure lines end with newline for consistent processing
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"

    offset = 0
    for hunk in hunks:
        old_start = hunk["old_start"] - 1 + offset  # 0-indexed
        hunk_lines = hunk["lines"]

        old_lines: list[str] = []
        new_lines: list[str] = []
        for hl in hunk_lines:
            if hl.startswith("-"):
                old_lines.append(hl[1:])
            elif hl.startswith("+"):
                new_lines.append(hl[1:])
            elif hl.startswith(" "):
                old_lines.append(hl[1:])
                new_lines.append(hl[1:])

        # Ensure trailing newlines
        old_lines = [l if l.endswith("\n") else l + "\n" for l in old_lines]
        new_lines = [l if l.endswith("\n") else l + "\n" for l in new_lines]

        end_idx = old_start + len(old_lines)
        lines[old_start:end_idx] = new_lines
        offset += len(new_lines) - len(old_lines)

    return "".join(lines)


def create_diff(original: str, modified: str, filename: str = "file") -> str:
    """Create a unified diff from original and modified content."""
    original_lines = original.splitlines(keepends=True)
    modified_lines = modified.splitlines(keepends=True)

    diff = difflib.unified_diff(
        original_lines,
        modified_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        lineterm="",
    )
    return "\n".join(diff)


def _strip_diff_prefix(path: str) -> str:
    """Strip a/ or b/ prefix from diff file paths."""
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path
