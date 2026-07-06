# app/services/documentation.py
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from app.services.ollama import generate

logger = logging.getLogger("avatar.documentation")

DOCUMENTATION_SYSTEM_PROMPT = """
You are Avatar's Documentation Engineer (Hermes 3 role).
Your responsibilities:
- Generate clean, accurate, and production-grade documentation (READMEs, changelogs, API specs, migration guides, and release notes).
- Ensure that documentation perfectly matches the implementation changes and code updates.

Return ONLY a JSON object with the following keys:
  - "documentation_changes": list[dict] (each with "path": str, "content": str, "type": "readme|changelog|api|other")
  - "summary": str (brief explanation of documentation updates)
Do NOT output any markdown, code fences, or text outside the JSON block.
"""

async def generate_project_documentation(project_id: str, code_changes: list[dict], plan: dict) -> Dict[str, Any]:
    """Propose documentation updates matching the implementation changes."""
    prompt = json.dumps({
        "project_id": project_id,
        "code_changes": code_changes,
        "plan": plan,
    }, indent=2)
    raw, ok = await generate(
        model="Avatar coding model",
        prompt=prompt,
        system=DOCUMENTATION_SYSTEM_PROMPT,
        role="planner",
    )
    if not ok:
        logger.error("Documentation Agent LLM unavailable")
        return {"error": "Documentation Agent unavailable"}
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception as e:
        logger.exception("Failed to parse documentation output: %s", e)
        return {"error": f"Parse error: {e}"}
