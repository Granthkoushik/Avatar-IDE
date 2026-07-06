from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from app.services.ollama import generate
from app.services.memory import get_plan, get_requirements

logger = logging.getLogger("avatar.reviewer")

# System prompt for code review – Qwen3 8B Reviewer Role
REVIEWER_SYSTEM_PROMPT = """
You are Avatar's Repository Intelligence & Reviewer (Qwen3 role).
Your responsibilities:
- Review generated code and detect bugs, missing imports/interfaces, inconsistencies, and architecture mismatches.
- Perform static analysis and reject low-quality or incomplete implementations.

Verification guidelines:
- Verify imports, dependencies, configuration, APIs, frontend/backend, database structures, security/authentication, routing, file/workspace operations, tests, and documentation.
- Ensure the project builds successfully and code is production-ready.

Return ONLY a JSON object with two keys:
  - "review_comments": list of objects {"path": str, "comment": str, "severity": str}
  - "summary": str (high-level review outcome).
Do NOT output raw code; focus on feedback.
"""

async def review_code(project_id: str, generated_changes: List[Dict[str, str]]) -> Dict[str, Any]:
    """Run the reviewer model on the generated code changes.
    `generated_changes` should be a list of file change dicts from the coder output.
    Returns structured JSON with review comments.
    """
    requirements = get_requirements(project_id) or {}
    plan = get_plan(project_id) or {}
    prompt = json.dumps({
        "requirements": requirements,
        "plan": plan,
        "generated_changes": generated_changes,
    }, indent=2)
    raw, ok = await generate(
        model="Avatar coding model",
        prompt=prompt,
        system=REVIEWER_SYSTEM_PROMPT,
        role="reviewer",
    )
    if not ok:
        logger.error("Reviewer LLM unavailable")
        return {"error": "Reviewer unavailable"}
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        result = json.loads(raw[start:end])
        # Determine if fixes are needed based on severity of comments
        comments = result.get("review_comments", [])
        needs_fix = any(c.get("severity", "").lower() in ("high", "critical") for c in comments)
        result["needs_fix"] = needs_fix
        logger.info("Reviewer output parsed successfully, needs_fix=%s", needs_fix)
        return result
    except Exception as e:
        logger.exception("Failed to parse reviewer output: %s", e)
        return {"error": f"Parse error: {e}"}

async def apply_review_comments(project_id: str, comments: List[Dict[str, str]]) -> List[str]:
    """Placeholder to handle review comments.
    In a full implementation this could trigger a follow‑up coding iteration.
    Here we simply log the comments and return affected paths.
    """
    affected = []
    for c in comments:
        path = c.get("path")
        if path:
            affected.append(path)
    logger.info("Review comments processed for paths: %s", affected)
    return affected
