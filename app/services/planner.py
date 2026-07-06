from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict

from app.services.ollama import generate
from app.services.memory import set_plan

logger = logging.getLogger("avatar.planner")

# ── Planner prompt demanding production-level detail ────────────────────────────
PLANNER_SYSTEM_PROMPT = """
You are Avatar's Chief Software Architect and Project Manager.

Your job: produce a COMPLETE, PRODUCTION-READY project plan.

Rules:
- Design real, working software. No stubs. No placeholders. No TODOs.
- List EVERY file the project needs, including: main entry, config, models, routes,
  services, tests, requirements.txt/package.json, README.md, Dockerfile (if needed).
- Each file entry must have:
    "name": exact relative file path (e.g. "app/models/user.py")
    "purpose": precise description of what this file implements
    "exports": list of class/function names it exports (for coder context)
    "depends_on": list of other file names this file imports from
- For Python projects: always include requirements.txt
- For Node projects: always include package.json

Return ONLY valid JSON with these exact keys:
{
  "goal": "one-line project goal",
  "tech_stack": ["Python", "FastAPI", ...],
  "requirements": ["..."],
  "constraints": ["..."],
  "architecture": "paragraph describing overall system architecture",
  "files": [
    {
      "name": "main.py",
      "purpose": "...",
      "exports": ["app", "main"],
      "depends_on": []
    }
  ],
  "tasks": [{"id": "1", "description": "...", "depends_on": []}],
  "implementation_steps": ["step 1", "step 2"]
}

Do NOT emit any text outside this JSON object.
"""

REQUIREMENTS_SYSTEM_PROMPT = """
You are Avatar's Requirements Analyst.
Extract structured requirements from the user's message.
Return ONLY valid JSON:
{
  "goal": "...",
  "features": ["..."],
  "tech_preferences": ["..."],
  "constraints": ["..."]
}
"""


async def analyze_requirements(project_id: str, user_input: str) -> Dict[str, Any]:
    """Analyze user input and return structured requirements."""
    raw, ok = await generate(
        model="Avatar coding model",
        prompt=f"User request:\n{user_input}",
        system=REQUIREMENTS_SYSTEM_PROMPT,
        role="planner",
    )
    if not ok:
        logger.error("Planner LLM unavailable")
        return {"goal": user_input, "features": [], "tech_preferences": [], "constraints": []}
    try:
        cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
        cleaned = re.sub(r"<thinking>.*?</thinking>", "", cleaned, flags=re.DOTALL).strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        data = json.loads(cleaned[start:end])
        logger.info("Requirements extracted: %s", data.get("goal"))
        return data
    except Exception as e:
        logger.exception("Failed to parse requirements: %s", e)
        return {"goal": user_input, "features": [], "tech_preferences": [], "constraints": []}


async def create_plan(project_id: str, requirements: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a full production project plan from requirements."""
    prompt = (
        "Generate a COMPLETE production project plan for:\n\n"
        f"Goal: {requirements.get('goal', '')}\n"
        f"Features: {json.dumps(requirements.get('features', []))}\n"
        f"Tech preferences: {json.dumps(requirements.get('tech_preferences', []))}\n"
        f"Constraints: {json.dumps(requirements.get('constraints', []))}\n\n"
        "Requirements:\n"
        "- Include ALL files needed for a working, deployable project\n"
        "- Include requirements.txt or package.json\n"
        "- Include a README.md\n"
        "- Include at least 2 test files\n"
        "- Production code only - no stubs or TODOs\n"
    )
    raw, ok = await generate(
        model="Avatar coding model",
        prompt=prompt,
        system=PLANNER_SYSTEM_PROMPT,
        role="planner",
    )
    if not ok:
        logger.error("Planner LLM unavailable during plan generation")
        return {"error": "Planner unavailable", "files": [], "goal": requirements.get("goal", "")}
    try:
        cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
        cleaned = re.sub(r"<thinking>.*?</thinking>", "", cleaned, flags=re.DOTALL).strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        plan = json.loads(cleaned[start:end])
        set_plan(project_id, plan)
        logger.info("Plan stored for project %s – %d files planned", project_id, len(plan.get("files", [])))
        return plan
    except Exception as e:
        logger.exception("Failed to parse plan output: %s", e)
        return {"error": f"Failed to parse plan: {e}", "files": [], "goal": requirements.get("goal", "")}
