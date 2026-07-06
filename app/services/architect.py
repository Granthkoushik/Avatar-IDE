# app/services/architect.py
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from app.services.ollama import generate
from app.services.memory import get_requirements

logger = logging.getLogger("avatar.architect")

ARCHITECT_SYSTEM_PROMPT = """
You are Avatar's Chief Software Architect and System Designer (Hermes 3 / DeepSeek-R1 role).
Your responsibilities:
- Design modular, scalable, maintainable, and high-performance software architecture.
- Define system structures, API schemas, routing patterns, database tables, and core module interfaces.
- Validate proposed architectures to prevent coupling and resource bottlenecks.

Return ONLY a JSON object with the following keys:
  - "architecture_summary": str (high-level architectural explanation)
  - "interfaces": list[dict] (each with "name", "type", "description", "methods")
  - "data_models": list[dict] (each with "name", "fields", "relationships")
  - "routing_flow": list[str] (step-by-step request flow)
Do NOT output any markdown, code fences, or text outside the JSON block.
"""

async def generate_architecture(project_id: str, plan: Dict[str, Any]) -> Dict[str, Any]:
    """Generate database schema, modules layout, and API interface routing."""
    requirements = get_requirements(project_id) or {}
    prompt = json.dumps({
        "requirements": requirements,
        "plan": plan,
    }, indent=2)
    raw, ok = await generate(
        model="Avatar coding model",
        prompt=prompt,
        system=ARCHITECT_SYSTEM_PROMPT,
        role="planner",
    )
    if not ok:
        logger.error("Architect LLM unavailable")
        return {"error": "Architect unavailable"}
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception as e:
        logger.exception("Failed to parse architect output: %s", e)
        return {"error": f"Parse error: {e}"}
