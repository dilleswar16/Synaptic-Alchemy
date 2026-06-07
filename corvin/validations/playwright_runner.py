"""Playwright script executor for Corvin validation engine.

Writes the uploaded script to a temp directory, runs it via
`npx playwright test --reporter=json`, parses structured results,
and returns a dict that is persisted into PlaywrightRunRow.result_json.

Requires Node.js + @playwright/test installed in the runtime environment:
    npm install -g @playwright/test
    npx playwright install chromium

If Playwright is not installed, returns a clear error result rather than raising.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_log = logging.getLogger(__name__)

_PLAYWRIGHT_CONFIG = """\
import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: '.',
  timeout: 30000,
  reporter: [['json', { outputFile: 'results.json' }]],
  use: { headless: true, ignoreHTTPSErrors: true },
});
"""


async def run_playwright_script(
    script_content: str,
    filename: str,
    timeout_seconds: int = 120,
) -> dict:
    """Execute a Playwright test script and return a structured result dict.

    Returns:
        {
            "passed": bool,
            "total": int,
            "failed_count": int,
            "duration_ms": int,
            "output": str,
            "tests": [{"title", "status", "duration_ms", "error"}, ...]
        }
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="corvin_pw_"))
    try:
        script_path = tmpdir / filename
        script_path.write_text(script_content, encoding="utf-8")
        (tmpdir / "playwright.config.ts").write_text(_PLAYWRIGHT_CONFIG, encoding="utf-8")

        start = datetime.now(timezone.utc)

        try:
            proc = await asyncio.create_subprocess_exec(
                "npx", "playwright", "test",
                str(script_path),
                "--config", str(tmpdir / "playwright.config.ts"),
                cwd=str(tmpdir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "CI": "1", "PLAYWRIGHT_JSON_OUTPUT_NAME": "results.json"},
            )
        except FileNotFoundError:
            return _not_installed_result()

        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return _timeout_result(timeout_seconds)

        duration_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
        stdout = (stdout_b or b"").decode("utf-8", errors="replace")
        stderr = (stderr_b or b"").decode("utf-8", errors="replace")
        combined = (stdout + ("\n" + stderr if stderr.strip() else "")).strip()

        # Prefer the JSON output file written by the reporter
        results_file = tmpdir / "results.json"
        if results_file.exists():
            try:
                report = json.loads(results_file.read_text(encoding="utf-8"))
                return _parse_report(report, combined, duration_ms)
            except (json.JSONDecodeError, KeyError):
                pass

        # Fallback: try to find JSON embedded in stdout
        return _parse_stdout(stdout, combined, duration_ms)

    except Exception as exc:
        _log.exception("Playwright execution failed: %s", exc)
        return _error_result(str(exc))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── Result parsers ────────────────────────────────────────────────────────────

def _parse_report(report: dict, output: str, duration_ms: int) -> dict:
    tests: list[dict] = []
    for suite in report.get("suites", []):
        tests.extend(_flatten_specs(suite))

    stats = report.get("stats", {})
    expected = int(stats.get("expected", 0))
    unexpected = int(stats.get("unexpected", 0))
    flaky = int(stats.get("flaky", 0))
    total = expected + unexpected if (expected + unexpected) > 0 else len(tests)
    failed_count = unexpected + flaky
    passed = failed_count == 0 and total > 0

    return {
        "passed": passed,
        "total": total,
        "failed_count": failed_count,
        "duration_ms": duration_ms,
        "output": output[:8000],
        "tests": tests,
    }


def _flatten_specs(suite: dict) -> list[dict]:
    results: list[dict] = []
    for spec in suite.get("specs", []):
        for test in spec.get("tests", []):
            run_result = (test.get("results") or [{}])[-1]
            status = run_result.get("status", "unknown")
            error: str | None = None
            err_obj = run_result.get("error")
            if err_obj:
                error = err_obj.get("message") or err_obj.get("value") or str(err_obj)
                if error:
                    error = error[:500]
            results.append({
                "title": test.get("title") or spec.get("title", "Test"),
                "status": status,
                "duration_ms": int(run_result.get("duration", 0)),
                "error": error,
            })
    for child in suite.get("suites", []):
        results.extend(_flatten_specs(child))
    return results


def _parse_stdout(stdout: str, combined: str, duration_ms: int) -> dict:
    """Fallback parser when results.json is not available."""
    passed_text = "passed" in stdout.lower()
    failed_text = "failed" in stdout.lower() or "error" in stdout.lower()
    passed = passed_text and not failed_text
    return {
        "passed": passed,
        "total": 1,
        "failed_count": 0 if passed else 1,
        "duration_ms": duration_ms,
        "output": combined[:8000],
        "tests": [{
            "title": "Script execution",
            "status": "passed" if passed else "failed",
            "duration_ms": duration_ms,
            "error": None if passed else (combined[:500] or "Script failed"),
        }],
    }


# ── Error helpers ─────────────────────────────────────────────────────────────

def _not_installed_result() -> dict:
    msg = (
        "Playwright / Node.js not found on this server.\n"
        "Install: npm install -g @playwright/test && npx playwright install chromium"
    )
    return {
        "passed": False, "total": 0, "failed_count": 1, "duration_ms": 0,
        "output": msg,
        "tests": [{"title": "Environment check", "status": "error", "duration_ms": 0, "error": msg}],
    }


def _timeout_result(timeout_seconds: int) -> dict:
    msg = f"Execution timed out after {timeout_seconds}s"
    return {
        "passed": False, "total": 0, "failed_count": 1,
        "duration_ms": timeout_seconds * 1000,
        "output": msg,
        "tests": [{"title": "Script execution", "status": "timedOut", "duration_ms": timeout_seconds * 1000, "error": msg}],
    }


def _error_result(message: str) -> dict:
    return {
        "passed": False, "total": 0, "failed_count": 1, "duration_ms": 0,
        "output": message,
        "tests": [{"title": "Execution error", "status": "error", "duration_ms": 0, "error": message[:500]}],
    }
