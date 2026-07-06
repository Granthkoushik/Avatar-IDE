# app/services/test_engine.py
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from app.services.ollama import generate

logger = logging.getLogger("avatar.test_engine")

TEST_ENGINE_SYSTEM_PROMPT = """
You are Avatar's Quality Assurance & Test Engineer (Hermes 3 / Qwen3 role).
Your responsibilities:
- Design testing strategies, identify verification paths, and generate robust unit tests.
- Verify imports, mocks, and execution paths of new and modified features.

Return ONLY a JSON object with the following keys:
  - "test_changes": list[dict] (each with "path": str, "content": str, "explanation": str)
  - "test_strategy_summary": str (brief summary of proposed verification method)
Do NOT output any markdown, code fences, or text outside the JSON block.
"""

async def generate_unit_tests(project_id: str, code_changes: list[dict], plan: dict) -> Dict[str, Any]:
    """Design and generate unit tests to verify implementation correctness."""
    prompt = json.dumps({
        "project_id": project_id,
        "code_changes": code_changes,
        "plan": plan,
    }, indent=2)
    raw, ok = await generate(
        model="Avatar coding model",
        prompt=prompt,
        system=TEST_ENGINE_SYSTEM_PROMPT,
        role="coder",
    )
    if not ok:
        logger.error("Test Engine LLM unavailable")
        return {"error": "Test Engine unavailable"}
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception as e:
        logger.exception("Failed to parse test engine output: %s", e)
        return {"error": f"Parse error: {e}"}
