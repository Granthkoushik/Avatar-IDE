"""Test intent classifier heuristic logic."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

from app.services.intent_classifier import _heuristic_classify, _is_question

# (message, expected_category_or_None)
tests = [
    # Should trigger pipeline
    ("build me a Jarvis voice assistant", "New Project"),
    ("create a full-stack todo app with React and FastAPI", "New Project"),
    ("make a Python web scraper", "New Project"),
    ("implement a REST API for user management", "New Project"),
    ("add a login endpoint to the API", "Feature Request"),
    ("fix the bug in the authentication module", "Bug Fix"),
    ("refactor the database layer", "Large Refactor"),
    ("write unit tests for the codebase", "Testing"),
    ("create a Dockerfile for this project", "Deployment"),
    ("I want a voice assistant chatbot", "New Project"),
    ("I need a CLI tool for file processing", "New Project"),
    # Should NOT trigger pipeline (questions / casual)
    ("what does create a FastAPI app look like?", None),
    ("how do I build a REST API?", None),
    ("explain how to create a web server", None),
    ("what is a dockerfile?", None),
    ("can you explain how the coder works?", None),
    ("hello", "Casual Chat"),
    ("thanks", "Casual Chat"),
    ("how are you", "Casual Chat"),
    ("tell me about yourself", "Casual Chat"),
]

passed = 0
failed = 0
for msg, expected_cat in tests:
    result = _heuristic_classify(msg)
    if expected_cat is None:
        ok = result is None
        got = "None (→ LLM)" if result is None else result["category"]
        exp = "None (→ LLM)"
    elif expected_cat == "Casual Chat":
        ok = result is not None and result["category"] == "Casual Chat"
        got = result["category"] if result else "None"
        exp = expected_cat
    else:
        ok = result is not None and result["category"] == expected_cat
        got = result["category"] if result else "None (→ LLM)"
        exp = expected_cat
    
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] '{msg[:55]}' → got={got} (expected={exp})")
    if ok: passed += 1
    else: failed += 1

print(f"\n{passed}/{passed+failed} passed")
