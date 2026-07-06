from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from app.services.ollama import generate
from app.services.memory import get_plan, get_requirements

logger = logging.getLogger("avatar.debugger")

# System prompt for debugging – DeepSeek-R1 / Qwen3 8B Role
DEBUGGER_SYSTEM_PROMPT = """
You are Avatar's Debugger and Reasoning Engineer (DeepSeek-R1 / Qwen3 role).
Your responsibilities:
- Given source code, error messages, execution logs, and test failures, perform strict root-cause analysis.
- Propose a minimal, precise fix targeting the source of the crash/failure (e.g. syntax bugs, logic errors, missing imports, NoneType, or unsafe indices).

Engineering Rules:
- Ensure the proposed change maintains repository standards and formatting.
- Avoid broad, unrelated rewrites; keep changes localized and complete.

Return ONLY a JSON object with two keys:
  - "file_changes": list of objects {"path": str, "diff": str, "explanation": str}
  - "summary": str (high‑level description of the fix).
Do NOT output raw code outside the JSON.
"""

async def debug_code(project_id: str, error_info: Dict[str, Any]) -> Dict[str, Any]:
    """Run the debugger model on the provided error information.
    `error_info` should contain keys like "code", "error", "logs", "test_failures".
    Returns the structured JSON described in the system prompt.
    """
    requirements = get_requirements(project_id) or {}
    plan = get_plan(project_id) or {}
    prompt = json.dumps({
        "requirements": requirements,
        "plan": plan,
        "error_info": error_info,
    }, indent=2)
    raw, ok = await generate(
        model="Avatar coding model",
        prompt=prompt,
        system=DEBUGGER_SYSTEM_PROMPT,
        role="debugger",
    )
    if not ok:
        logger.error("Debugger LLM unavailable")
        return {"error": "Debugger unavailable"}
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        result = json.loads(raw[start:end])
        logger.info("Debugger output parsed successfully")
        return result
    except Exception as e:
        logger.exception("Failed to parse debugger output: %s", e)
        return {"error": f"Parse error: {e}"}

async def apply_debug_changes(project_id: str, changes: List[Dict[str, str]]) -> List[str]:
    """Apply debugger file changes using the secure file manager.
    Returns list of modified file paths.
    """
    modified = []
    from app.services.file_manager import secure_write_file, _resolve_path
    from app.services.coder import apply_patch
    for change in changes:
        path = change.get("path")
        diff = change.get("diff")
        if not path or not diff:
            continue
        try:
            try:
                target_path = _resolve_path(project_id, path)
                original_content = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
            except Exception:
                original_content = ""
            
            new_content = apply_patch(original_content, diff)
            secure_write_file(project_id, path, new_content)
            modified.append(path)
        except Exception as e:
            logger.error("Failed to write %s during debugging: %s", path, e)
    return modified
