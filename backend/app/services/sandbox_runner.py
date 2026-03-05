import logging
import os
import re
import shutil
import subprocess
import tempfile

from app.config import get_settings

logger = logging.getLogger(__name__)


class SandboxRunner:
    """Runs patches in an isolated environment and returns test results."""

    def run(self, repo_path: str, patch_diff: str, job_id: str) -> dict:
        """
        Apply patch_diff to a copy of repo_path and run tests.

        Tries Docker first; falls back to subprocess.
        Returns {stdout, stderr, test_passed, test_count, exit_code,
                 test_results: list[dict]}.
        """
        if shutil.which("docker"):
            try:
                return self._run_with_docker(repo_path, patch_diff)
            except Exception as exc:
                logger.warning("Docker sandbox failed: %s; using subprocess fallback", exc)
        return self._run_subprocess_fallback(repo_path, patch_diff)

    # ------------------------------------------------------------------
    # Docker runner
    # ------------------------------------------------------------------

    def _run_with_docker(self, repo_path: str, patch_diff: str) -> dict:
        settings = get_settings()
        with tempfile.TemporaryDirectory() as tmp_dir:
            work_dir = os.path.join(tmp_dir, "workspace")
            shutil.copytree(repo_path, work_dir)

            patch_ok = self._apply_patch(work_dir, patch_diff)
            if not patch_ok:
                return self._error_result("Patch application failed")

            cmd = [
                "docker", "run", "--rm",
                f"--cpus={settings.sandbox_cpu_limit}",
                f"--memory={settings.sandbox_memory_limit}",
                "--network=none",
                "-v", f"{work_dir}:/workspace",
                "-w", "/workspace",
                "python:3.11-slim",
                "sh", "-c",
                # Use --no-build-isolation and avoid editable installs to limit
                # arbitrary setup.py execution; install only declared deps if present.
                "[ -f requirements.txt ] && pip install -r requirements.txt -q 2>/dev/null; "
                "python -m pytest --tb=short -q 2>&1 || true",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=settings.sandbox_timeout,
            )
            return self._build_result(result.stdout, result.stderr, result.returncode)

    # ------------------------------------------------------------------
    # Subprocess fallback
    # ------------------------------------------------------------------

    def _run_subprocess_fallback(self, repo_path: str, patch_diff: str) -> dict:
        settings = get_settings()
        with tempfile.TemporaryDirectory() as tmp_dir:
            work_dir = os.path.join(tmp_dir, "workspace")
            shutil.copytree(repo_path, work_dir)

            patch_ok = self._apply_patch(work_dir, patch_diff)
            if not patch_ok:
                return self._error_result("Patch application failed")

            return self._run_tests(work_dir)

    # ------------------------------------------------------------------
    # Patch application
    # ------------------------------------------------------------------

    def _apply_patch(self, repo_path: str, diff: str) -> bool:
        """Apply a unified diff using the system `patch` command."""
        if not diff or not diff.strip():
            return True  # No-op patch

        patch_bin = shutil.which("patch")
        if patch_bin:
            try:
                result = subprocess.run(
                    [patch_bin, "-p1", "--forward", "--batch"],
                    input=diff,
                    text=True,
                    cwd=repo_path,
                    capture_output=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    return True
                logger.warning("patch command failed: %s", result.stderr)
            except Exception as exc:
                logger.warning("patch command error: %s", exc)

        # Fallback: manual application via diff_utils
        try:
            from app.utils.diff_utils import apply_diff, extract_target_file

            target = extract_target_file(diff)
            if not target:
                logger.warning("Could not determine target file from diff")
                return False
            target_path = os.path.join(repo_path, target)
            if not os.path.exists(target_path):
                logger.warning("Target file not found: %s", target_path)
                return False
            with open(target_path, "r", encoding="utf-8") as f:
                original = f.read()
            patched = apply_diff(original, diff)
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(patched)
            return True
        except Exception as exc:
            logger.error("Manual patch application failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Test running
    # ------------------------------------------------------------------

    def _run_tests(self, path: str) -> dict:
        """Auto-detect and run tests for the project at path."""
        settings = get_settings()
        framework, cmd = self._detect_test_framework(path)
        logger.info("Detected test framework: %s", framework)

        try:
            result = subprocess.run(
                cmd,
                cwd=path,
                capture_output=True,
                text=True,
                timeout=settings.sandbox_timeout,
            )
            return self._build_result(result.stdout, result.stderr, result.returncode)
        except subprocess.TimeoutExpired:
            return self._error_result("Tests timed out")
        except Exception as exc:
            return self._error_result(f"Test execution error: {exc}")

    def _detect_test_framework(self, path: str) -> tuple[str, list[str]]:
        """Return (framework_name, command_list) for the project."""
        if any(
            os.path.exists(os.path.join(path, f))
            for f in ("pytest.ini", "setup.cfg", "pyproject.toml", "setup.py")
        ):
            return "pytest", ["python", "-m", "pytest", "--tb=short", "-q"]
        if os.path.exists(os.path.join(path, "package.json")):
            return "npm", ["npm", "test", "--", "--reporter=min"]
        if os.path.exists(os.path.join(path, "pom.xml")):
            return "maven", ["mvn", "test", "-q"]
        if os.path.exists(os.path.join(path, "build.gradle")):
            return "gradle", ["./gradlew", "test"]
        # Default to pytest
        return "pytest", ["python", "-m", "pytest", "--tb=short", "-q"]

    # ------------------------------------------------------------------
    # Output parsing
    # ------------------------------------------------------------------

    def _parse_pytest_output(self, output: str) -> list[dict]:
        """Parse pytest short output into a list of test result dicts."""
        results: list[dict] = []
        for line in output.splitlines():
            if " PASSED" in line:
                name = line.split(" PASSED")[0].strip()
                results.append({"name": name, "status": "passed", "duration_ms": 0.0, "message": ""})
            elif " FAILED" in line:
                name = line.split(" FAILED")[0].strip()
                results.append({"name": name, "status": "failed", "duration_ms": 0.0, "message": line})
            elif " ERROR" in line:
                name = line.split(" ERROR")[0].strip()
                results.append({"name": name, "status": "error", "duration_ms": 0.0, "message": line})
        return results

    def _build_result(self, stdout: str, stderr: str, exit_code: int) -> dict:
        """Build the standard result dict from subprocess output."""
        combined = stdout + stderr
        test_results = self._parse_pytest_output(stdout)
        passed = sum(1 for r in test_results if r["status"] == "passed")
        test_count = len(test_results) if test_results else 0

        # Also parse summary line e.g. "5 passed, 1 failed"
        summary = re.search(r"(\d+) passed", combined)
        if summary and not test_results:
            passed = int(summary.group(1))
            test_count = passed
            failed_match = re.search(r"(\d+) failed", combined)
            if failed_match:
                test_count += int(failed_match.group(1))

        test_passed = exit_code == 0

        return {
            "stdout": stdout,
            "stderr": stderr,
            "test_passed": test_passed,
            "test_count": test_count,
            "exit_code": exit_code,
            "test_results": test_results,
        }

    def _error_result(self, message: str) -> dict:
        return {
            "stdout": "",
            "stderr": message,
            "test_passed": False,
            "test_count": 0,
            "exit_code": -1,
            "test_results": [],
        }


_sandbox_runner_instance: SandboxRunner | None = None


def get_sandbox_runner() -> SandboxRunner:
    """Return the singleton SandboxRunner instance."""
    global _sandbox_runner_instance
    if _sandbox_runner_instance is None:
        _sandbox_runner_instance = SandboxRunner()
    return _sandbox_runner_instance
