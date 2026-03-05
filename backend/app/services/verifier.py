import logging
import re

logger = logging.getLogger(__name__)


class Verifier:
    """Scores a sandbox result to estimate patch confidence."""

    _RISK_PATTERNS: list[tuple[str, re.Pattern]] = [
        ("eval(", re.compile(r"\beval\s*\(", re.IGNORECASE)),
        ("exec(", re.compile(r"\bexec\s*\(", re.IGNORECASE)),
        ("os.system(", re.compile(r"\bos\.system\s*\(", re.IGNORECASE)),
        ("password=", re.compile(r"\bpassword\s*=", re.IGNORECASE)),
        ("credentials", re.compile(r"\bcredentials\b", re.IGNORECASE)),
        ("subprocess.call(", re.compile(r"\bsubprocess\.(?:call|Popen|run)\s*\(", re.IGNORECASE)),
        ("__import__(", re.compile(r"\b__import__\s*\(", re.IGNORECASE)),
        ("compile(", re.compile(r"\bcompile\s*\(", re.IGNORECASE)),
    ]

    def score(self, sandbox_result: dict, repo_path: str = "") -> dict:
        """
        Score a sandbox result across multiple dimensions.

        Returns {score: int, evidence: list[{component, score, weight, details}]}.
        """
        evidence: list[dict] = []
        combined_output = (
            sandbox_result.get("stdout", "")
            + sandbox_result.get("stderr", "")
        )

        # 1. Reproducer success (weight 0.40)
        reproducer_score = 100 if sandbox_result.get("test_passed", False) else 0
        evidence.append(
            {
                "component": "reproducer_success",
                "score": reproducer_score,
                "weight": 0.40,
                "details": "Tests passed" if reproducer_score else "Tests failed or not run",
            }
        )

        # 2. Unit test pass rate (weight 0.25)
        test_count = sandbox_result.get("test_count", 0)
        test_results: list[dict] = sandbox_result.get("test_results", [])
        if test_count > 0:
            passed = sum(1 for t in test_results if t.get("status") == "passed")
            if not test_results:
                passed = test_count if sandbox_result.get("test_passed") else 0
            unit_test_score = int((passed / test_count) * 100)
        else:
            unit_test_score = 50  # No tests; neutral
        evidence.append(
            {
                "component": "unit_test_pass_rate",
                "score": unit_test_score,
                "weight": 0.25,
                "details": f"{test_count} tests found",
            }
        )

        # 3. Lint and static analysis (weight 0.10)
        stderr = sandbox_result.get("stderr", "")
        error_count = len(re.findall(r"\berror\b", stderr, re.IGNORECASE))
        lint_score = max(0, 100 - error_count * 20) if error_count > 0 else 100
        evidence.append(
            {
                "component": "lint_and_static_ok",
                "score": lint_score,
                "weight": 0.10,
                "details": f"{error_count} error(s) in stderr",
            }
        )

        # 4. Coverage delta (weight 0.10)
        coverage_score = self._coverage_delta_score(combined_output)
        evidence.append(
            {
                "component": "coverage_delta",
                "score": coverage_score,
                "weight": 0.10,
                "details": "Coverage parsed from output",
            }
        )

        # 5. Heuristic risk penalty (weight 0.15)
        risk_score = self._risk_penalty(combined_output)
        evidence.append(
            {
                "component": "heuristic_risk_penalty",
                "score": risk_score,
                "weight": 0.15,
                "details": "Scanned output for risky patterns",
            }
        )

        final_score = sum(e["score"] * e["weight"] for e in evidence)
        final_score = max(0, min(100, round(final_score)))

        return {"score": final_score, "evidence": evidence}

    def _coverage_delta_score(self, output: str) -> int:
        """Parse coverage percentage from output and score accordingly."""
        # Look for patterns like "TOTAL ... 85%"
        matches = re.findall(r"(\d{1,3})%", output)
        if not matches:
            return 50  # Neutral – no coverage data
        try:
            last_pct = int(matches[-1])
            if last_pct >= 80:
                return 80
            if last_pct >= 60:
                return 60
            return 30
        except ValueError:
            return 50

    def _risk_penalty(self, output: str) -> int:
        """Deduct 20 points per risky pattern found in output, floor at 0."""
        hits = sum(1 for _, regex in self._RISK_PATTERNS if regex.search(output))
        return max(0, 100 - hits * 20)


_verifier_instance: Verifier | None = None


def get_verifier() -> Verifier:
    """Return the singleton Verifier instance."""
    global _verifier_instance
    if _verifier_instance is None:
        _verifier_instance = Verifier()
    return _verifier_instance
