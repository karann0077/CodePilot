import logging
import math
import re

logger = logging.getLogger(__name__)


class SecretsScanner:
    """Scans text for secrets and sensitive data patterns."""

    PATTERNS: dict[str, str] = {
        "aws_access_key": r"AKIA[0-9A-Z]{16}",
        "github_token": r"gh[pousr]_[A-Za-z0-9_]{36,}",
        "api_key": r"(?i)api[_-]?key\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{20,}",
        "password": r"(?i)password\s*[=:]\s*['\"]?[^\s'\"]{8,}",
        "private_key": r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY",
        "jwt": r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
        "connection_string": r"(?:postgresql|mysql|mongodb|redis)://[^\s\"']+",
    }
    # Entropy threshold: 4.5 bits/char is well above natural-language text (~3.5)
    # but typical of Base64-encoded keys, tokens, and high-randomness secrets.
    # Min length of 20 chars avoids false positives on short identifiers.
    _ENTROPY_THRESHOLD = 4.5
    _ENTROPY_MIN_LEN = 20

    def __init__(self) -> None:
        self._compiled: dict[str, re.Pattern] = {
            name: re.compile(pattern)
            for name, pattern in self.PATTERNS.items()
        }

    def scan(self, text: str) -> list[dict]:
        """Scan text and return list of {type, value, start, end} matches."""
        findings: list[dict] = []
        for secret_type, pattern in self._compiled.items():
            for match in pattern.finditer(text):
                findings.append(
                    {
                        "type": secret_type,
                        "value": match.group(0),
                        "start": match.start(),
                        "end": match.end(),
                    }
                )

        # High-entropy string detection
        token_pattern = re.compile(r"[A-Za-z0-9+/=_\-]{20,}")
        for match in token_pattern.finditer(text):
            token = match.group(0)
            if len(token) >= self._ENTROPY_MIN_LEN and self.entropy(token) > self._ENTROPY_THRESHOLD:
                # Avoid duplicate with already-matched patterns
                already_flagged = any(
                    f["start"] <= match.start() < f["end"] for f in findings
                )
                if not already_flagged:
                    findings.append(
                        {
                            "type": "high_entropy_string",
                            "value": token,
                            "start": match.start(),
                            "end": match.end(),
                        }
                    )

        findings.sort(key=lambda x: x["start"])
        return findings

    def redact(self, text: str) -> str:
        """Replace detected secrets with [REDACTED:{type}] placeholders."""
        findings = self.scan(text)
        # Process in reverse order to preserve positions
        result = text
        for finding in reversed(findings):
            placeholder = f"[REDACTED:{finding['type']}]"
            result = result[: finding["start"]] + placeholder + result[finding["end"] :]
        return result

    def has_secrets(self, text: str) -> bool:
        """Return True if text contains any detected secrets."""
        return len(self.scan(text)) > 0

    @staticmethod
    def entropy(s: str) -> float:
        """Calculate Shannon entropy of a string."""
        if not s:
            return 0.0
        freq: dict[str, int] = {}
        for ch in s:
            freq[ch] = freq.get(ch, 0) + 1
        length = len(s)
        return -sum(
            (count / length) * math.log2(count / length)
            for count in freq.values()
            if count > 0
        )


_scanner_instance: SecretsScanner | None = None


def get_secrets_scanner() -> SecretsScanner:
    """Return the singleton SecretsScanner instance."""
    global _scanner_instance
    if _scanner_instance is None:
        _scanner_instance = SecretsScanner()
    return _scanner_instance
