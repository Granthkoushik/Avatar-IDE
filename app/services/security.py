# app/services/security.py
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from app.services.ollama import generate

logger = logging.getLogger("avatar.security")

SECURITY_SYSTEM_PROMPT = """
You are Avatar's Security Reviewer and Audit Engineer (Qwen3 8B role).
Your responsibilities:
- Inspect code changes for security flaws (command injections, SQL injections, hardcoded secrets, unsafe file access, XSS, eval/exec execution, or TLS verification bypass).
- Report clear vulnerabilities and suggest mitigations.

Return ONLY a JSON object with the following keys:
  - "vulnerabilities": list[dict] (each with "title", "severity": "low|medium|high|critical", "description", "file", "line", "mitigation")
  - "security_passed": bool
Do NOT output any markdown, code fences, or text outside the JSON block.
"""

async def audit_code_changes(project_id: str, changes: list[dict]) -> Dict[str, Any]:
    """Inspect and audit code changes for vulnerabilities."""
    prompt = json.dumps({
        "project_id": project_id,
        "changes": changes,
    }, indent=2)
    raw, ok = await generate(
        model="Avatar coding model",
        prompt=prompt,
        system=SECURITY_SYSTEM_PROMPT,
        role="reviewer",
    )
    if not ok:
        logger.error("Security Agent LLM unavailable")
        return {"error": "Security Agent unavailable"}
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception as e:
        logger.exception("Failed to parse security audit output: %s", e)
        return {"error": f"Parse error: {e}"}
