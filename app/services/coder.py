from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from app.services.ollama import generate
from app.services.memory import get_requirements
from app.services.auto_namer import sanitize_path

logger = logging.getLogger("avatar.coder")

# ── Coder system prompt ─────────────────────────────────────────────────────────
CODER_SYSTEM_PROMPT = """
You are Avatar's Senior Software Engineer producing PRODUCTION-READY code.

STRICT RULES – NEVER BREAK THEM:
1. Generate COMPLETE, WORKING code. No stubs. No "# TODO". No "pass" as placeholder.
   Every function must have a real implementation.
2. Every import must exist. If you import a library, ensure it is in requirements.txt.
3. Code must be syntactically valid – it will be executed immediately.
4. Handle errors properly. Use try/except, proper status codes, logging.
5. Include type hints for all Python functions.
6. Follow PEP 8 for Python. Use async/await where appropriate (FastAPI routes MUST be async).
7. For web apps: include CORS, error handlers, proper response models.
8. For databases: include proper connection handling, transactions, and migrations.
9. For tests: tests must actually test real functionality, not just assert True.

OUTPUT FORMAT:
Output ONLY the complete file content inside a single fenced code block.
Example:
```python
# complete file content here
```
Do NOT output any explanation, preamble, or other text outside the code block.
The code block must contain the ENTIRE file, ready to save and run directly.
"""


def _build_project_context(files_list: list[dict], current_file: str) -> str:
    """Build rich cross-file context so the coder understands the full project."""
    other_files = [f for f in files_list if f.get("name") != current_file]
    if not other_files:
        return ""

    lines = ["PROJECT FILE STRUCTURE (other files in this project):"]
    for f in other_files:
        name = f.get("name", "")
        purpose = f.get("purpose", "")
        exports = f.get("exports", [])
        depends = f.get("depends_on", [])
        lines.append(f"\n  File: {name}")
        lines.append(f"  Purpose: {purpose}")
        if exports:
            lines.append(f"  Exports: {', '.join(exports)}")
        if depends:
            lines.append(f"  Depends on: {', '.join(depends)}")
    return "\n".join(lines)


async def generate_code(project_id: str, plan: Dict[str, Any]) -> Dict[str, Any]:
    """Generate production-quality code for all files in the plan."""
    requirements = get_requirements(project_id) or {}
    files_list = plan.get("files", [])
    goal = plan.get("goal", "")
    tech_stack = plan.get("tech_stack", [])
    architecture = plan.get("architecture", "")

    if not files_list:
        logger.warning("No files in plan – generating single fallback file")
        return await _generate_single_file(project_id, plan, requirements)

    logger.info("Generating %d files for project %s", len(files_list), project_id)
    file_changes = []
    summary_parts = []

    for idx, f_info in enumerate(files_list):
        f_name = f_info.get("name", "")
        f_purpose = f_info.get("purpose", "")
        f_exports = f_info.get("exports", [])
        f_depends = f_info.get("depends_on", [])
        if not f_name:
            continue

        logger.info("[%d/%d] Generating: %s", idx + 1, len(files_list), f_name)

        project_context = _build_project_context(files_list, f_name)

        prompt = f"""Project Goal: {goal}
Tech Stack: {', '.join(tech_stack)}
Architecture: {architecture}

{project_context}

NOW GENERATE THE FOLLOWING FILE:
File: {f_name}
Purpose: {f_purpose}
This file should export: {', '.join(f_exports) if f_exports else 'see purpose'}
This file depends on: {', '.join(f_depends) if f_depends else 'none'}

Requirements extracted from user:
{json.dumps(requirements, indent=2)}

CRITICAL: Generate the COMPLETE, PRODUCTION-READY implementation of {f_name}.
Output ONLY the file content in a fenced code block. No explanation text outside the block.
"""
        raw, ok = await generate(
            model="Avatar coding model",
            prompt=prompt,
            system=CODER_SYSTEM_PROMPT,
            role="coder",
        )
        if not ok:
            logger.error("LLM unavailable for file %s", f_name)
            continue

        f_content, explanation = _parse_coder_output(raw, f_name)
        if not f_content:
            logger.warning("Empty content for %s – skipping", f_name)
            continue

        clean_path = sanitize_path(f_name, f_content)
        file_changes.append({
            "path": clean_path,
            "diff": f_content,
            "explanation": explanation,
        })
        summary_parts.append(f"Generated {clean_path}")
        logger.info("  → wrote %s (%d chars)", clean_path, len(f_content))

    return {
        "file_changes": file_changes,
        "summary": "; ".join(summary_parts),
    }


def _parse_coder_output(raw: str, filename: str) -> tuple[str, str]:
    """Robustly parse the coder LLM output into (content, explanation).
    
    Handles: fenced code blocks, thinking tags, JSON wrapping, raw output.
    """
    if not raw:
        return "", ""

    # 1. Strip reasoning/thinking tags (DeepSeek-R1, Qwen3 thinking mode)
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    cleaned = re.sub(r"<thinking>.*?</thinking>", "", cleaned, flags=re.DOTALL)
    cleaned = cleaned.strip()

    # 2. Prefer fenced code block (most reliable for coding models)
    code_match = re.search(r"```(?:[a-zA-Z0-9_+-]*)\n(.*?)```", cleaned, re.DOTALL)
    if code_match:
        content = code_match.group(1).strip()
        if content and len(content) > 20:
            return content, f"Generated {filename}"

    # 3. Try JSON parsing (for models that wrap code in JSON)
    try:
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start != -1 and end > start:
            result = json.loads(cleaned[start:end])
            content = result.get("content", "")
            explanation = result.get("explanation", f"Generated {filename}")
            if content and len(content) > 20:
                return content.strip(), explanation
    except Exception:
        pass

    # 4. Last resort: use raw if it looks substantial enough to be code
    if len(cleaned) > 50:
        logger.warning("Using raw output for %s (%d chars)", filename, len(cleaned))
        return cleaned, f"Raw output for {filename}"

    return "", ""


async def _generate_single_file(project_id: str, plan: Dict[str, Any], requirements: dict) -> Dict[str, Any]:
    """Fallback: generate a single file from the plan description."""
    prompt = json.dumps({"requirements": requirements, "plan": plan}, indent=2)
    raw, ok = await generate(
        model="Avatar coding model",
        prompt=prompt,
        system=CODER_SYSTEM_PROMPT,
        role="coder",
    )
    if not ok:
        return {"file_changes": [], "summary": "No code generated – LLM unavailable"}
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        result = json.loads(raw[start:end])
        for fc in result.get("file_changes", []):
            fc["path"] = sanitize_path(fc.get("path", ""), fc.get("diff", ""))
        return result
    except Exception as e:
        return {"error": f"Parse error: {e}", "file_changes": []}


# ── Patch application ──────────────────────────────────────────────────────────

def apply_patch(original_content: str, patch_content: str) -> str:
    """Apply a unified diff patch OR return patch_content as full replacement."""
    lines = original_content.splitlines(keepends=True)
    patch_lines = patch_content.splitlines()

    if not any(l.startswith(("+++", "---", "@@")) for l in patch_lines[:10]):
        # Not a diff – treat as full replacement
        return patch_content

    result_lines = list(lines)
    i = 0
    while i < len(patch_lines):
        line = patch_lines[i]
        if line.startswith("@@"):
            match = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            if match:
                old_start = int(match.group(1)) - 1
                int(match.group(2))  # new_start parsed but not needed for context-free patch
                i += 1
                old_lines: List[str] = []
                new_lines: List[str] = []
                while i < len(patch_lines) and not patch_lines[i].startswith("@@"):
                    pl = patch_lines[i]
                    if pl.startswith("-"):
                        old_lines.append(pl[1:] + "\n")
                    elif pl.startswith("+"):
                        new_lines.append(pl[1:] + "\n")
                    else:
                        ctx = pl[1:] if pl.startswith(" ") else pl
                        old_lines.append(ctx + "\n")
                        new_lines.append(ctx + "\n")
                    i += 1
                # Apply chunk
                for j, ol in enumerate(old_lines):
                    idx = old_start + j
                    if idx < len(result_lines):
                        if j < len(new_lines):
                            result_lines[idx] = new_lines[j]
                        else:
                            result_lines[idx] = None  # type: ignore[assignment]
                result_lines = [l for l in result_lines if l is not None]
            else:
                i += 1
        else:
            i += 1
    return "".join(result_lines)


async def apply_file_changes(project_id: str, changes: list[dict]) -> list[str]:
    """Write generated file changes to disk. Returns list of file paths written."""
    from app.services.file_manager import secure_write_file, _resolve_path
    modified = []
    for change in changes:
        path = change.get("path", "")
        diff = change.get("diff", "")
        if not path or not diff:
            continue
        try:
            try:
                target_path = _resolve_path(project_id, path)
                original = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
            except Exception:
                original = ""

            # If original file exists and diff looks like a unified patch, apply patch;
            # otherwise use diff/content as the full file.
            new_content = apply_patch(original, diff) if original else diff
            secure_write_file(project_id, path, new_content)
            modified.append(path)
            logger.info("Wrote: %s/%s", project_id, path)
        except Exception as e:
            logger.error("Failed to write %s: %s", path, e)
    return modified
