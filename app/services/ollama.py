from __future__ import annotations

import json
from collections.abc import AsyncIterator
from fastapi import HTTPException

import httpx

from app.services.config_manager import get_setting, get_config

OLLAMA_URL = "http://localhost:11434"

def get_registered_models() -> set[str]:
    cfg = get_config()
    models = {
        "Avatar coding model",
        "Avatar_Coding:latest",
        "Avatar:latest"
    }
    ai_models_section = cfg.get("ai_models", {}) if cfg else {}
    for k, v in ai_models_section.items():
        if isinstance(v, dict) and "model_name" in v:
            models.add(v["model_name"])
    return models

def get_allowed_base_models() -> set[str]:
    registered = get_registered_models()
    base_models = {
        "qwen2.5-coder",
        "deepseek-coder",
        "codellama",
        "llama3",
        "tinyllama",
        "nemotron-3-ultra",
        "avatar",
        "avatar_coding"
    }
    for m in registered:
        base_name = m.split(":")[0].lower()
        base_models.add(base_name)
    return base_models

def validate_model(model_name: str) -> None:
    """Validate that the requested model is whitelisted or a tag of an allowed base model."""
    allowed = get_registered_models()
    if model_name in allowed:
        return
    base_name = model_name.split(":")[0].lower()
    if base_name in get_allowed_base_models():
        return
    raise HTTPException(
        status_code=400,
        detail=f"Model '{model_name}' is not allowed. Allowed models: {sorted(allowed)}",
    )

CODING_SYSTEM_PROMPT = """You are AVATAR, a production-grade autonomous AI Software Engineering Platform.
You function as an intelligent software engineering organization capable of understanding, planning, building, modifying, debugging, testing, documenting, securing, deploying, and continuously improving complete software systems.

Core mission & behavior:
- Transform user ideas into production-ready software while minimizing manual effort.
- Prefer precise, runnable code over vague advice.
- Match the requested language and idioms.
- When asked to write, create, implement, generate, build, or fix code, output a complete solution inside a single fenced code block with the correct language tag.
- Keep explanations brief outside code fences.
- Never refuse to write code when asked; produce the best working draft you can.

Engineering Philosophy:
- Inspect before modifying, understand before implementing, and plan before coding.
- Review before accepting, test before delivering, and optimize after correctness.
- Document every meaningful change.
- Never leave the repository in a worse state than before.
"""

def sort_models_prefer_role(models: list[str], role: str) -> list[str]:
    """Sort models giving priority based on role‑specific hints."""
    # Lookup which model is routed for this role
    routing = get_setting(f"model_routing.{role}")
    primary_model = ""
    if routing:
        model_cfg = get_setting(f"ai_models.{routing}")
        if model_cfg and "model_name" in model_cfg:
            primary_model = model_cfg["model_name"].lower()
            
    ranked: list[tuple[int, int, str]] = []
    for index, name in enumerate(models):
        lower = name.lower()
        if primary_model and primary_model in lower:
            priority = 0
        else:
            priority = 1
        ranked.append((priority, index, name))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [name for _, _, name in ranked]

# Map code role names to their config keys in system.yaml
_ROLE_TO_CONFIG_KEY: dict[str, str] = {
    "coder": "code_generation",
    "planner": "planner",
    "debugger": "debugger",
    "reviewer": "code_review",
    "security": "security",
    "tester": "testing",
    "docs": "documentation",
    "architect": "planner",
    "rag": "rag",
    "analyzer": "repository_analysis",
}

# Fallback models in preference order (all confirmed installed by user)
_FALLBACK_MODELS_BY_ROLE: dict[str, str] = {
    "coder": "qwen2.5-coder:14b",
    "planner": "hermes3:latest",
    "debugger": "deepseek-r1:8b",
    "reviewer": "qwen3:8b",
    "security": "qwen3:8b",
    "tester": "hermes3:latest",
    "docs": "hermes3:latest",
    "architect": "hermes3:latest",
    "analyzer": "qwen3:8b",
}
_DEFAULT_FALLBACK = "hermes3:latest"

async def resolve_role_model(role: str, requested: str) -> str:
    """Map a role to a concrete Ollama model name using the config routing table.
    Falls back to known-good local models if config or model is unavailable.
    """
    # Translate role alias to config key
    config_key = _ROLE_TO_CONFIG_KEY.get(role, role)

    # Try config routing first
    routing = get_setting(f"model_routing.{config_key}")
    if routing:
        model_cfg = get_setting(f"ai_models.{routing}")
        if model_cfg and "model_name" in model_cfg:
            model_name = model_cfg["model_name"]
            # Skip cloud/placeholder model names
            if "cloud" not in model_name.lower() and "avatar" not in model_name.lower():
                return model_name

    # If a real model was explicitly requested (not the placeholder), use it
    if requested and requested != "Avatar coding model":
        return requested

    # Fallback to known-good local model for this role
    return _FALLBACK_MODELS_BY_ROLE.get(role, _DEFAULT_FALLBACK)

async def list_models() -> list[str]:
    """Retrieve list of models from Ollama and include the Avatar placeholder."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            models = [m["name"] for m in data.get("models", [])]
    except Exception:
        models = []
    if "Avatar coding model" not in models:
        models.append("Avatar coding model")
    return models

async def generate(model: str, prompt: str, system: str = CODING_SYSTEM_PROMPT, role: str = "coder") -> tuple[str, bool]:
    """Generate a response from Ollama using the specified model and role.
    Returns (response_text, success). On failure returns ("", False).
    """
    # Validate model against whitelist before proceeding
    validate_model(model)
    resolved_model = await resolve_role_model(role, model)
    import logging
    _log = logging.getLogger("avatar.ollama")
    _log.info("generate() role=%s resolved_model=%s", role, resolved_model)
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:  # 5 min for large codegen
            response = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": resolved_model,
                    "prompt": prompt,
                    "system": system,
                    "stream": False,
                    "options": {"num_predict": 4096},
                },
            )
            response.raise_for_status()
            text = response.json().get("response", "")
            _log.info("generate() got %d chars from %s", len(text), resolved_model)
            return text, True
    except Exception as exc:
        _log.error("generate() failed for role=%s model=%s: %s", role, resolved_model, exc)
        return "", False

async def stream_generate(model: str, prompt: str, system: str = CODING_SYSTEM_PROMPT, role: str = "coder") -> AsyncIterator[str]:
    # Validate model against whitelist before streaming
    validate_model(model)
    resolved_model = await resolve_role_model(role, model)
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST",
            f"{OLLAMA_URL}/api/generate",
            json={"model": resolved_model, "prompt": prompt, "system": system, "stream": True},
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                payload = json.loads(line)
                yield payload.get("response", "")
                if payload.get("done"):
                    break
