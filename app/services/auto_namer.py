"""app/services/auto_namer.py

Autonomous file name and extension detection engine.

Given raw generated code content (and optionally a declared path hint),
infer the canonical filename with the correct extension that should be
used to persist this file on the workspace filesystem.
"""
from __future__ import annotations

import re
import logging
from pathlib import Path

logger = logging.getLogger("avatar.auto_namer")

# ── Extension map keyed by detected technology signal ──────────────────────────
_EXT_SIGNALS: list[tuple[list[str], str]] = [
    # Web front-end
    (["<!doctype html", "<html", "<head>", "<body>"], ".html"),
    (["@import ", ":root {", "body {", ".container", "margin:", "padding:", "#app {"], ".css"),
    # React / JSX (must precede JS)
    (["import react", "from 'react'", 'from "react"', "usestate(", "useeffect(", "jsx"], ".tsx"),
    # JavaScript
    (["require(", "module.exports", "import express", "const express", "app.get(", "app.post(", "app.listen("], ".js"),
    # TypeScript  
    (["interface ", ": string;", ": number;", "type props =", "export type "], ".ts"),
    # Python – must come BEFORE SQL to catch "from fastapi import …"
    (["from fastapi", "from flask", "from django", "import uvicorn",
      "if __name__ == '__main__'", "async def ", "@app.get", "@app.post",
      "def __init__(self", "cls, ", "self,", "@pytest", "@dataclass",
      "import asyncio", "import os\n", "from pathlib"], ".py"),
    # SQL – use multi-word patterns to avoid false positives with Python imports
    (["create table ", "insert into ", "select * from", "alter table ", "drop table ",
      "primary key", "foreign key", "inner join", "left join", "where id ="], ".sql"),
    # YAML / Docker-compose
    (["version:", "services:", "volumes:", "image:", "build:"], ".yml"),
    # Dockerfile
    (["from python:", "from node:", "from ubuntu:", "run apt-get", "cmd [", "expose ", "workdir /"], "Dockerfile"),
    # Shell
    (["#!/bin/bash", "#!/bin/sh", "#!/usr/bin/env bash", "echo ", "chmod ", "export path="], ".sh"),
    # Makefile
    (["all:", ".phony:", "$(make)", "cc ", "gcc "], "Makefile"),
    # JSON config
    (['"name":', '"version":', '"dependencies":', '"scripts":'], ".json"),
    # TOML
    (["[tool.poetry]", "[project]", "python_requires", "[build-system]"], ".toml"),
    # requirements
    (["==", ">=", "<=", "~="], "requirements.txt"),
    # Python (fallback; must remain last)
    (["import ", "from ", "def ", "class ", "print(", "if __name__"], ".py"),
]

# ── Purpose-based name templates ───────────────────────────────────────────────
_PURPOSE_NAMES: list[tuple[list[str], str]] = [
    # Main entry point (must come before routes/api)
    (["if __name__ == '__main__'", "uvicorn.run", "main()"], "main"),
    # Server / HTTP
    (["import express", "const express", "app.listen(", "listen(3000", "listen(8000"], "server"),
    # Deployment
    (["dockerfile", "from python:", "from node:", "from ubuntu:", "run apt"], "Dockerfile"),
    # README docs
    (["# installation", "## usage", "## getting started", "## features"], "README"),
    # Database / SQL
    (["create table", "insert into", "schema", "migration"], "schema"),
    (["sqlite3", "sqlalchemy", "database", "db.execute", "db.session"], "database"),
    # Auth
    (["jwt", "bcrypt", "password", "login", "register", "auth"], "auth"),
    # Models / ORM (check before routes to avoid "model" matching routes)
    (["basemodel", "declarative_base", "dataclass"], "models"),
    # Config / Settings
    (["config", "settings", "env", "environment", "dotenv"], "config"),
    # Tests
    (["unittest", "pytest", "def test_", "describe(", "it("], "test"),
    # Middleware
    (["middleware", "cors", "request intercept"], "middleware"),
    # API / routing (broad — must come after more specific entries)
    (["fastapi", "flask", "django", "router", "app.get", "app.post", "routes"], "routes"),
    # Utils / helpers
    (["helper", "utility", "utils", "format_", "parse_", "convert_"], "utils"),
    # Styles
    (["@import", ":root", "body {", "font-family", "color:", "background:"], "styles"),
    # Frontend app entry
    (["<!doctype html", "<html", "<head>"], "index"),
]


def _detect_extension(content_lower: str) -> str:
    """Return the most likely file extension based on code signals."""
    for signals, ext in _EXT_SIGNALS:
        if any(sig in content_lower for sig in signals):
            return ext
    return ".py"  # safe default


def _detect_base_name(content_lower: str, path_hint: str = "") -> str:
    """Derive a semantic file base-name from code patterns or path hint."""
    # If path_hint already has a clean name, prefer it
    if path_hint:
        stem = Path(path_hint).stem
        if stem and stem.lower() not in {"untitled", "file", "code", "output", "main"}:
            return stem

    # Scan purpose patterns
    for signals, name in _PURPOSE_NAMES:
        for sig in signals:
            try:
                if re.search(sig, content_lower):
                    return name
            except re.error:
                if sig in content_lower:
                    return name

    # Attempt to extract class or function name
    class_match = re.search(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]+)", content_lower)
    if class_match:
        return _to_snake(class_match.group(1))

    fn_match = re.search(r"\bdef\s+([A-Za-z_][A-Za-z0-9_]+)", content_lower)
    if fn_match:
        name = fn_match.group(1)
        if name not in {"main", "test", "run"}:
            return _to_snake(name)

    return "app"


def _to_snake(name: str) -> str:
    """Convert CamelCase / PascalCase to snake_case."""
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return s.lower()


def _special_filename(ext: str, base: str) -> str:
    """Handle files without extensions (Dockerfile, Makefile, README)."""
    no_ext = {".dockerfile": "Dockerfile", ".makefile": "Makefile", ".readme": "README.md"}
    if ext in no_ext:
        return no_ext[ext]
    if ext == "Dockerfile":
        return "Dockerfile"
    if ext == "Makefile":
        return "Makefile"
    if ext == "requirements.txt":
        return "requirements.txt"
    return f"{base}{ext}"


def infer_filename(content: str, path_hint: str = "") -> str:
    """
    Given code content and an optional path hint, return the most appropriate
    filename (with extension) for the file.

    Examples
    --------
    >>> infer_filename("CREATE TABLE users ...")
    'schema.sql'
    >>> infer_filename("import express\\napp.get('/',...)")
    'server.js'
    >>> infer_filename("class AuthManager:\\n    def login(self, ...")
    'auth_manager.py'
    """
    if not content or not content.strip():
        # No content at all — keep untitled hint if present
        if path_hint:
            return Path(path_hint).name or "untitled"
        return "untitled"

    content_lower = content.lower()
    ext = _detect_extension(content_lower)
    base = _detect_base_name(content_lower, path_hint)

    filename = _special_filename(ext, base)
    logger.debug("auto_namer: path_hint=%r → filename=%r", path_hint, filename)
    return filename


def sanitize_path(raw_path: str, content: str = "") -> str:
    """
    Sanitize a file path produced by the LLM.

    - Strips leading slash / drive prefix that would escape the project root
    - Infers missing or bad extension from content when needed
    - Replaces 'untitled' stems with auto-detected name
    """
    if not raw_path:
        return infer_filename(content)

    p = Path(raw_path.strip().lstrip("/\\"))
    stem = p.stem.lower()
    suffix = p.suffix.lower()

    # Stem is bad → replace
    if not stem or stem in {"untitled", "file", "code", "output"}:
        new_name = infer_filename(content, raw_path)
        return str(p.parent / new_name) if str(p.parent) not in {".", ""} else new_name

    # Extension is missing or too generic
    if not suffix or suffix == ".txt":
        detected_ext = _detect_extension(content.lower()) if content else ".py"
        if detected_ext and detected_ext != "Dockerfile" and detected_ext != "Makefile":
            p = p.with_suffix(detected_ext)

    return p.as_posix()
