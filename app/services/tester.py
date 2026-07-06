from __future__ import annotations

import logging
import re
from pathlib import Path
from app.services.executor import execute_command

logger = logging.getLogger("avatar.tester")

async def detect_test_command(project_dir: Path) -> str:
    """Scan project structure and determine the appropriate test runner command."""
    # Check for Python pytest or unittest
    requirements = project_dir / "requirements.txt"
    package_json = project_dir / "package.json"
    cargo_toml = project_dir / "Cargo.toml"
    
    if cargo_toml.exists():
        return "cargo test"
        
    if package_json.exists():
        # Check npm scripts
        try:
            import json
            data = json.loads(package_json.read_text(encoding="utf-8"))
            if "test" in data.get("scripts", {}):
                return "npm test"
        except Exception:
            pass
        return "npx jest"
        
    if requirements.exists():
        content = requirements.read_text(encoding="utf-8")
        if "pytest" in content:
            return "pytest"
            
    # Check for test files in python
    for p in project_dir.glob("**/test_*.py"):
        return "pytest"
        
    # Return a basic default python testing command
    return "python -m unittest discover"

async def run_project_tests(project_dir: Path) -> dict:
    """Run tests for the project and parse stdout/stderr for results."""
    cmd = await detect_test_command(project_dir)
    res = await execute_command(cmd, project_dir, timeout=60.0)
    
    # Parse test counts
    passed = 0
    failed = 0
    total = 0
    
    output = res.stdout + "\n" + res.stderr
    
    # Match pytest output, e.g. "2 passed, 1 failed in 0.12s"
    pytest_match = re.search(r"=(\s*(?P<passed>\d+)\s*passed)?(,\s*(?P<failed>\d+)\s*failed)?.*in\s+[\d.]+s\s*=", output)
    if pytest_match:
        passed = int(pytest_match.group("passed") or 0)
        failed = int(pytest_match.group("failed") or 0)
        total = passed + failed
    else:
        # Match standard unittest output, e.g., "Ran 5 tests in 0.003s\n\nFAILED (failures=1)" or "OK"
        unittest_ran = re.search(r"Ran\s+(?P<total>\d+)\s+test", output)
        if unittest_ran:
            total = int(unittest_ran.group("total"))
            unittest_failed = re.search(r"FAILED\s*\(.*failures=(?P<failures>\d+).*\)", output)
            unittest_errors = re.search(r"FAILED\s*\(.*errors=(?P<errors>\d+).*\)", output)
            failed = int(unittest_failed.group("failures") or 0) if unittest_failed else 0
            failed += int(unittest_errors.group("errors") or 0) if unittest_errors else 0
            passed = total - failed
        else:
            # Check for npm test / jest outputs, e.g., "Tests:       3 failed, 12 passed, 15 total"
            jest_match = re.search(r"Tests:\s+(?:(?P<failed>\d+)\s+failed,\s+)?(?:(?P<passed>\d+)\s+passed,\s+)?(?P<total>\d+)\s+total", output)
            if jest_match:
                total = int(jest_match.group("total") or 0)
                passed = int(jest_match.group("passed") or 0)
                failed = int(jest_match.group("failed") or 0)
            else:
                # Fallback heuristics
                if res.exit_code == 0:
                    passed = 1
                    total = 1
                else:
                    failed = 1
                    total = 1

    return {
        "command": cmd,
        "stdout": res.stdout,
        "stderr": res.stderr,
        "exit_code": res.exit_code,
        "duration": res.duration,
        "passed": passed,
        "failed": failed,
        "total": total,
        "success": res.exit_code == 0
    }
