# app/services/intent_classifier.py
from __future__ import annotations

import json
import logging
import re
from typing import Any
from app.services.ollama import generate

logger = logging.getLogger("avatar.intent_classifier")

CLASSIFICATION_SYSTEM_PROMPT = """
You are Avatar's Intent Classifier (Hermes 3 role).
You classify user inputs to optimize pipeline execution.

Classify the user's input into exactly ONE of the following categories:
- Casual Chat (greetings, simple chat, unrelated topics)
- General Question (programming questions not asking to modify/create files in this workspace)
- Documentation (generating READMEs, API descriptions, logs)
- Repository Analysis (asking to explain, scan, or summarize codebase layout)
- Bug Fix (fixing compilation, logic bugs, traceback errors, crash reports)
- Feature Request (implementing new code blocks, routes, pages)
- Architecture (system design, database schemas, APIs design)
- Large Refactor (renaming modules, restructuring packages)
- New Project (creating a new app, framework scaffolding)
- Testing (writing unit or integration tests)
- Deployment (dockerfiles, build configs)

Return ONLY a JSON object with the keys:
  - "category": str (one of the categories above)
  - "confidence": float (between 0.0 and 1.0)
  - "reasoning": str (brief explanation)
Do NOT output markdown fences or other text.
"""

# ── Casual patterns – these ALWAYS return Casual Chat immediately ───────────────
_CASUAL_PHRASES = {
    "hello", "hi", "hey", "how are you", "who are you",
    "good morning", "good afternoon", "good evening", "thanks", "thank you",
    "ok", "okay", "cool", "nice", "great", "awesome", "sure", "yes", "no",
    "what is avatar", "tell me about yourself", "what can you do",
}

# ── Patterns that indicate a QUESTION (should NOT trigger pipeline) ─────────────
_QUESTION_PREFIXES = (
    "what ", "why ", "how ", "when ", "where ", "which ", "who ",
    "can you explain", "explain ", "tell me ", "describe ", "show me how",
    "what does", "what is", "what are", "how do", "how does", "how can",
    "is it possible", "could you explain", "what's the difference",
)

# ── Strong BUILD intent patterns (must look like direct commands) ───────────────
# Each entry is (pattern_list, category). Patterns are matched only when the
# message does NOT start with a question word and is clearly imperative.
_BUILD_PATTERNS: list[tuple[re.Pattern, str]] = [
    # New Project – must start sentence with a build verb
    (re.compile(
        r"^(build|create|make|write|implement|develop|scaffold|generate|"
        r"set up|setup|initialize|init|start|spin up|spin-up|code|design|"
        r"program)\s+(me\s+)?(a|an|the|my|our|new|full|complete|entire|"
        r"simple|basic|advanced|production|real|working)?\s+\w",
        re.IGNORECASE
    ), "New Project"),
    # i want / i need / give me + something built
    (re.compile(
        r"^(i\s+want|i\s+need|i\s+would\s+like|give\s+me|show\s+me)\s+"
        r"(a|an|the|my|some)?\s*(complete|full|working|production|new)?\s*"
        r"(app|application|project|system|tool|script|bot|api|server|service|"
        r"website|web\s+app|cli|dashboard|backend|frontend|database|db|"
        r"chatbot|voice\s+assistant|assistant)\b",
        re.IGNORECASE
    ), "New Project"),
    # Feature Request – add/implement something to existing codebase
    (re.compile(
        r"^(add|implement|integrate|include|enable|plug\s+in|hook\s+up|"
        r"wire\s+up|set\s+up|connect)\s+(a|an|the|some)?\s*"
        r"(feature|endpoint|route|api|page|view|component|module|service|"
        r"function|class|method|handler|middleware|plugin|hook)\b",
        re.IGNORECASE
    ), "Feature Request"),
    # Bug Fix – explicit fix command
    (re.compile(
        r"^(fix|repair|debug|resolve|patch|correct|solve|handle|address)\s+"
        r"(the|this|a|an|that)?\s*(bug|error|crash|issue|problem|exception|"
        r"traceback|failure|warning|warning|lint|type\s+error|runtime\s+error|"
        r"compilation|import\s+error)\b",
        re.IGNORECASE
    ), "Bug Fix"),
    # Large Refactor
    (re.compile(
        r"^(refactor|restructure|reorganize|rewrite|rename|modularize|"
        r"clean\s+up|extract|split)\s+(the|this|my|our|all)?\s*",
        re.IGNORECASE
    ), "Large Refactor"),
    # Testing
    (re.compile(
        r"^(write|generate|create|add)\s+(unit|integration|end-to-end|e2e|"
        r"functional|regression)?\s*tests?\b",
        re.IGNORECASE
    ), "Testing"),
    # Deployment
    (re.compile(
        r"^(create|write|generate|build|set\s+up|configure)\s+(a|an|the)?\s*"
        r"(dockerfile|docker\s+compose|ci/cd|github\s+actions|k8s|kubernetes|"
        r"helm|nginx|deployment|pipeline)\b",
        re.IGNORECASE
    ), "Deployment"),
]


def _is_question(message: str) -> bool:
    """Return True if the message looks like a question or explanation request."""
    lower = message.strip().lower()
    if lower.endswith("?"):
        return True
    for prefix in _QUESTION_PREFIXES:
        if lower.startswith(prefix):
            return True
    return False


def _heuristic_classify(message: str) -> dict[str, Any] | None:
    """Fast heuristic classification without LLM calls.
    Returns a classification dict or None if the LLM should decide.
    """
    lower = message.strip().lower()
    clean = re.sub(r"[^\w\s]", " ", lower).strip()

    # 1. Casual phrases
    if clean in _CASUAL_PHRASES or len(clean.split()) <= 2:
        for phrase in _CASUAL_PHRASES:
            if clean == phrase or clean.startswith(phrase + " "):
                return {"category": "Casual Chat", "confidence": 1.0,
                        "reasoning": "Greeting or casual phrase detected."}

    # 2. If it looks like a question → let LLM decide (don't force pipeline)
    if _is_question(message):
        return None  # Fall through to LLM

    # 3. Check strong build patterns
    msg = message.strip()
    for pattern, category in _BUILD_PATTERNS:
        if pattern.match(msg):
            logger.info("Heuristic pattern matched → %s", category)
            return {"category": category, "confidence": 0.92,
                    "reasoning": f"Strong imperative build pattern matched: {category}"}

    return None  # Fall through to LLM


async def classify_intent(message: str) -> dict[str, Any]:
    """Classify user intent using fast heuristics first, then LLM fallback."""
    heuristic = _heuristic_classify(message)
    if heuristic is not None:
        return heuristic

    # LLM classification
    raw, ok = await generate(
        model="Avatar coding model",
        prompt=f"User message: {message}",
        system=CLASSIFICATION_SYSTEM_PROMPT,
        role="planner"
    )
    if not ok:
        # LLM unavailable – conservative fallback: never trigger pipeline on failure
        return {"category": "General Question", "confidence": 0.5,
                "reasoning": "LLM unavailable, conservative fallback."}

    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception:
        return {"category": "General Question", "confidence": 0.5,
                "reasoning": "Failed to parse LLM classification output."}
