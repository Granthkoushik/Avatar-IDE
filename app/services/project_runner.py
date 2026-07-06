"""app/services/project_runner.py

Autonomous project build runner for Avatar.

Handles:
- Dependency installation (pip / npm / cargo)
- Project startup validation (can the entry-point run without crashing?)
- Import-only syntax validation
- Producing structured execution reports for the debug loop
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from app.services.executor import execute_command

logger = logging.getLogger("avatar.project_runner")

_VENV_PYTHON = sys.executable  # the Python that runs this server


async def install_dependencies(project_dir: Path) -> dict[str, Any]:
    """Install project dependencies detected in the project directory."""
    results = []

    req_file = project_dir / "requirements.txt"
    if req_file.exists():
        content = req_file.read_text(encoding="utf-8").strip()
        if content:
            logger.info("Installing Python dependencies from requirements.txt")
            res = await execute_command(
                f'"{_VENV_PYTHON}" -m pip install -r requirements.txt -q --no-warn-script-location',
                project_dir,
                timeout=120.0,
            )
            results.append({
                "type": "pip",
                "exit_code": res.exit_code,
                "stdout": res.stdout[-2000:],
                "stderr": res.stderr[-2000:],
                "success": res.exit_code == 0,
            })
            if res.exit_code != 0:
                logger.warning("pip install failed:\n%s", res.stderr[-1000:])

    package_json = project_dir / "package.json"
    if package_json.exists():
        logger.info("Installing Node dependencies from package.json")
        res = await execute_command("npm install --silent", project_dir, timeout=120.0)
        results.append({
            "type": "npm",
            "exit_code": res.exit_code,
            "stdout": res.stdout[-2000:],
            "stderr": res.stderr[-2000:],
            "success": res.exit_code == 0,
        })

    return {
        "success": all(r["success"] for r in results) if results else True,
        "steps": results,
    }


async def syntax_check_python(project_dir: Path) -> dict[str, Any]:
    """Syntax-validate all Python files using py_compile (fast, no imports)."""
    errors = []
    py_files = list(project_dir.rglob("*.py"))
    for py_file in py_files:
        if "__pycache__" in py_file.parts:
            continue
        rel = py_file.relative_to(project_dir).as_posix()
        res = await execute_command(
            f'"{_VENV_PYTHON}" -m py_compile "{py_file}"',
            project_dir,
            timeout=10.0,
        )
        if res.exit_code != 0:
            errors.append({"file": rel, "error": res.stderr.strip()})

    return {"success": len(errors) == 0, "syntax_errors": errors}


async def run_entry_point(project_dir: Path, timeout: float = 15.0) -> dict[str, Any]:
    """
    Attempt to run the project's entry point for a short time.
    Success = no Python crash on startup (exit_code 0 OR running server = timeout without crash).
    """
    # Detect entry point
    candidates = ["main.py", "app.py", "server.py", "run.py", "src/main.py", "src/app.py"]
    entry = None
    for c in candidates:
        if (project_dir / c).exists():
            entry = c
            break

    if entry is None:
        # Try index.js for Node
        if (project_dir / "index.js").exists():
            res = await execute_command(
                "node --check index.js",
                project_dir,
                timeout=10.0,
            )
            return {
                "entry": "index.js",
                "exit_code": res.exit_code,
                "stdout": res.stdout[:2000],
                "stderr": res.stderr[:2000],
                "success": res.exit_code == 0,
                "note": "Node syntax check",
            }
        return {"entry": None, "success": True, "note": "No entry point found – skipping run check"}

    # Run with a short timeout – if it crashes immediately it's a failure
    res = await execute_command(
        f'"{_VENV_PYTHON}" {entry}',
        project_dir,
        timeout=timeout,
    )

    # A server that stays running will "time out" — that is OK.
    timed_out = "[AVATAR] Command timed out!" in (res.stdout + res.stderr)
    crashed = not timed_out and res.exit_code != 0

    return {
        "entry": entry,
        "exit_code": res.exit_code,
        "stdout": res.stdout[:3000],
        "stderr": res.stderr[:3000],
        "timed_out": timed_out,
        "crashed": crashed,
        "success": not crashed,
    }


async def full_validation(project_dir: Path) -> dict[str, Any]:
    """
    Full project validation sequence:
    1. Syntax check all Python files
    2. Install dependencies
    3. Run entry point (short-lived smoke test)

    Returns a unified report.
    """
    report: dict[str, Any] = {"success": True, "steps": [], "errors": []}

    # Step 1: Syntax check
    syntax = await syntax_check_python(project_dir)
    report["steps"].append({"name": "syntax_check", **syntax})
    if not syntax["success"]:
        report["success"] = False
        for e in syntax["syntax_errors"]:
            report["errors"].append(f"SyntaxError in {e['file']}: {e['error']}")
        return report  # No point installing if syntax is broken

    # Step 2: Install deps
    deps = await install_dependencies(project_dir)
    report["steps"].append({"name": "dependency_install", **deps})
    if not deps["success"]:
        report["success"] = False
        for s in deps["steps"]:
            if not s["success"]:
                report["errors"].append(f"Dependency install failed ({s['type']}): {s['stderr'][-500:]}")

    # Step 3: Entry point smoke test
    run = await run_entry_point(project_dir)
    report["steps"].append({"name": "entry_point_run", **run})
    if not run.get("success", True):
        report["success"] = False
        report["errors"].append(
            f"Entry point {run.get('entry')} crashed:\n"
            f"STDOUT: {run.get('stdout', '')[-800:]}\n"
            f"STDERR: {run.get('stderr', '')[-800:]}"
        )

    return report


def estimate_project_eta(plan: dict) -> tuple[int, str]:
    """
    Estimate project build time in seconds from the plan.
    Returns (seconds, human_readable_string).
    """
    files = plan.get("files", [])
    tasks = plan.get("tasks", [])
    goal = plan.get("goal", "").lower()

    file_count = len(files) if files else max(len(tasks), 3)

    # Base: 90 seconds per file (LLM generation + write)
    base = file_count * 90

    # Complexity multipliers
    complexity_words = ["full-stack", "microservices", "distributed", "real-time",
                        "machine learning", "ai", "neural", "database", "authentication",
                        "payment", "oauth", "websocket", "streaming"]
    multiplier = 1.0
    for word in complexity_words:
        if word in goal:
            multiplier += 0.3

    # Pipeline overhead: RAG + analyze + plan + arch + git + security + review + tests + debug + docs
    pipeline_overhead = 180  # ~3 minutes fixed overhead

    total_seconds = int(base * multiplier) + pipeline_overhead
    total_seconds = max(120, total_seconds)  # minimum 2 minutes

    if total_seconds < 3600:
        minutes = total_seconds // 60
        human = f"~{minutes} minutes"
    elif total_seconds < 86400:
        hours = total_seconds / 3600
        human = f"~{hours:.1f} hours"
    else:
        days = total_seconds / 86400
        human = f"~{days:.1f} days"

    return total_seconds, human
