import logging
import re

logger = logging.getLogger(__name__)


class Verifier:
    """Scores sandbox results using a weighted confidence formula."""

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
        Score a sandbox result across weighted components.

        Formula (normalized 0..1):
          conf = w_t*t + w_l*l + w_m*m + w_s*s - w_d*d
        with defaults:
          w_t=0.45, w_l=0.15, w_m=0.20, w_s=0.10, w_d=0.10
        """
        combined_output = sandbox_result.get("stdout", "") + sandbox_result.get("stderr", "")

        test_fraction = self._test_pass_fraction(sandbox_result)
        lint_score = self._lint_score(sandbox_result.get("stderr", ""))
        model_confidence = self._model_confidence(sandbox_result)
        sandbox_stability = 0.0 if sandbox_result.get("timed_out", False) else 1.0
        diff_norm = self._normalized_diff_size(sandbox_result)

        weights = {"t": 0.45, "l": 0.15, "m": 0.20, "s": 0.10, "d": 0.10}
        conf = (
            weights["t"] * test_fraction
            + weights["l"] * lint_score
            + weights["m"] * model_confidence
            + weights["s"] * sandbox_stability
            - weights["d"] * diff_norm
        )

        # Additional safety penalty from risky patterns in outputs.
        risk_penalty = self._risk_penalty(combined_output)
        conf = max(0.0, min(1.0, conf - risk_penalty))

        evidence = [
            {
                "component": "test_pass_fraction",
                "score": round(test_fraction, 3),
                "weight": weights["t"],
                "details": "Fraction of passing tests",
            },
            {
                "component": "lint_score",
                "score": round(lint_score, 3),
                "weight": weights["l"],
                "details": "stderr-derived lint quality",
            },
            {
                "component": "model_confidence",
                "score": round(model_confidence, 3),
                "weight": weights["m"],
                "details": "Parsed from patch metadata; defaults to neutral",
            },
            {
                "component": "sandbox_stability",
                "score": round(sandbox_stability, 3),
                "weight": weights["s"],
                "details": "0 if timeout/crash, else 1",
            },
            {
                "component": "normalized_diff_size",
                "score": round(diff_norm, 3),
                "weight": -weights["d"],
                "details": "Penalty for large diffs",
            },
            {
                "component": "risk_penalty",
                "score": round(risk_penalty, 3),
                "weight": -1.0,
                "details": "Penalty from risky patterns in logs/output",
            },
        ]

        return {"score": round(conf * 100), "evidence": evidence}

    def _test_pass_fraction(self, sandbox_result: dict) -> float:
        test_count = int(sandbox_result.get("test_count", 0) or 0)
        test_results: list[dict] = sandbox_result.get("test_results", [])
        if test_count <= 0:
            return 1.0 if sandbox_result.get("test_passed", False) else 0.0

        if test_results:
            passed = sum(1 for t in test_results if t.get("status") == "passed")
        else:
            passed = test_count if sandbox_result.get("test_passed", False) else 0
        return max(0.0, min(1.0, passed / test_count))

    def _lint_score(self, stderr: str) -> float:
        error_count = len(re.findall(r"\berror\b", stderr, re.IGNORECASE))
        return max(0.0, min(1.0, 1.0 - 0.2 * error_count))

    def _model_confidence(self, sandbox_result: dict) -> float:
        value = sandbox_result.get("model_confidence")
        if value is None:
            return 0.5
        try:
            numeric = float(value)
            if numeric > 1.0:
                numeric = numeric / 100.0
            return max(0.0, min(1.0, numeric))
        except (TypeError, ValueError):
            return 0.5

    def _normalized_diff_size(self, sandbox_result: dict) -> float:
        diff_lines = int(sandbox_result.get("diff_lines", 0) or 0)
        return max(0.0, min(1.0, diff_lines / 500.0))

    def _risk_penalty(self, output: str) -> float:
        hits = sum(1 for _, regex in self._RISK_PATTERNS if regex.search(output))
        return min(0.2, hits * 0.03)


_verifier_instance: Verifier | None = None


def get_verifier() -> Verifier:
    """Return the singleton Verifier instance."""
    global _verifier_instance
    if _verifier_instance is None:
        _verifier_instance = Verifier()
    return _verifier_instance
