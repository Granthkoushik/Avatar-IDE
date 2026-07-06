from __future__ import annotations

import json
import re

# Editor + review + execution languages
SUPPORTED_LANGUAGES = {
    "python",
    "javascript",
    "typescript",
    "jsx",
    "react",
    "html",
    "css",
    "json",
    "java",
    "kotlin",
    "csharp",
    "go",
    "rust",
    "c",
    "cpp",
    "ruby",
    "php",
    "sql",
    "bash",
    "powershell",
    "r",
    "lua",
    "scala",
    "swift",
}

# Monaco editor mapping for syntax highlighting
MONACO_LANGUAGE_MAP = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "typescript",
    "jsx": "javascript",
    "react": "javascript",
    "html": "html",
    "css": "css",
    "json": "json",
    "java": "java",
    "kotlin": "kotlin",
    "csharp": "csharp",
    "go": "go",
    "rust": "rust",
    "c": "c",
    "cpp": "cpp",
    "ruby": "ruby",
    "php": "php",
    "sql": "sql",
    "bash": "shell",
    "powershell": "powershell",
    "r": "r",
    "lua": "lua",
    "scala": "scala",
    "swift": "swift",
}


def detect_language(code: str, selected: str = "auto") -> str:
    if selected in SUPPORTED_LANGUAGES:
        return selected

    stripped = code.strip()
    if not stripped:
        return "python"

    if stripped.startswith("#!"):
        if "pwsh" in stripped.lower() or "powershell" in stripped.lower():
            return "powershell"
        return "bash"

    if stripped.startswith("<?php"):
        return "php"

    if stripped.startswith("<!doctype") or re.search(
        r"<html[\s>]", stripped, re.I
    ):
        return "html"

    if _looks_like_html_fragment(stripped) and not _looks_like_jsx(stripped):
        return "html"

    try:
        json.loads(stripped)
        return "json"
    except Exception:
        pass

    if _looks_like_sql(stripped):
        return "sql"

    if _looks_like_css_only(stripped):
        return "css"

    if _looks_like_react(stripped):
        return "react"

    if _looks_like_jsx(stripped):
        return "jsx"

    if re.search(r"\b(interface|type\s+\w+\s*=|:\s*(string|number|boolean)\b)", stripped):
        return "typescript"

    if _looks_like_java(stripped):
        return "java"

    if _looks_like_kotlin(stripped):
        return "kotlin"

    if _looks_like_csharp(stripped):
        return "csharp"

    if _looks_like_go(stripped):
        return "go"

    if _looks_like_rust(stripped):
        return "rust"

    if _looks_like_cpp(stripped):
        return "cpp"

    if _looks_like_c(stripped):
        return "c"

    if _looks_like_scala(stripped):
        return "scala"

    if _looks_like_swift(stripped):
        return "swift"

    if _looks_like_python(stripped):
        return "python"

    if _looks_like_ruby(stripped):
        return "ruby"

    if _looks_like_lua(stripped):
        return "lua"

    if _looks_like_r(stripped):
        return "r"

    if _looks_like_powershell(stripped):
        return "powershell"

    if _looks_like_bash(stripped):
        return "bash"

    if _looks_like_php(stripped):
        return "php"

    if _looks_like_javascript(stripped):
        return "javascript"

    return "python"


def monaco_language(language: str) -> str:
    return MONACO_LANGUAGE_MAP.get(language, "python")


def _looks_like_html_fragment(text: str) -> bool:
    return bool(re.search(r"<(head|body|div|section|button|p|span|script|style|meta)\b", text, re.I))


def _looks_like_jsx(text: str) -> bool:
    return bool(
        re.search(r"<\s*[A-Za-z][\w.-]*[^/>]*/?\s*>", text)
        and re.search(r"\b(function|const|let|var|export|import)\b", text)
    )


def _looks_like_react(text: str) -> bool:
    return bool(
        re.search(r"\b(useState|useEffect|useRef|useMemo|useCallback|React\.)\b", text)
        or re.search(r"from\s+['\"]react['\"]", text)
        or re.search(r"import\s+React\b", text)
        or (
            _looks_like_jsx(text)
            and re.search(r"\b(useState|useEffect|export\s+default)\b", text)
        )
    )


def _looks_like_sql(text: str) -> bool:
    return bool(
        re.search(
            r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE\s+TABLE|DROP\s+TABLE|ALTER\s+TABLE|WITH)\b",
            text,
            re.I,
        )
    )


def _looks_like_css_only(text: str) -> bool:
    if re.search(r"[{};]", text) and re.search(r"^\s*[@#.a-zA-Z][\w-]*\s*\{", text, re.M):
        return not re.search(r"\b(function|def |class |import |public |#include)\b", text)
    return False


def _looks_like_java(text: str) -> bool:
    return bool(
        re.search(r"\b(public\s+class|class\s+\w+|System\.out\.print|public\s+static\s+void\s+main)\b", text)
    )


def _looks_like_kotlin(text: str) -> bool:
    if re.search(r"\b(public\s+class|System\.out)\b", text):
        return False
    return bool(re.search(r"\b(fun\s+\w+|val\s+\w+|var\s+\w+)\b", text)) and "def " not in text


def _looks_like_csharp(text: str) -> bool:
    return bool(
        re.search(r"\b(using\s+System|namespace\s+\w+|Console\.Write|public\s+class|static\s+void\s+Main)\b", text)
    )


def _looks_like_go(text: str) -> bool:
    return bool(re.search(r"\b(package\s+main|func\s+main|fmt\.Print)", text))


def _looks_like_rust(text: str) -> bool:
    return bool(re.search(r"\b(fn\s+main|println!|use\s+std::|let\s+mut\s+)", text))


def _looks_like_cpp(text: str) -> bool:
    return bool(
        re.search(r"\b(#include\s*<|std::|cout\s*<<|using\s+namespace\s+std)", text)
        or (re.search(r"\bint\s+main\s*\(", text) and "printf" not in text and "stdio.h" not in text)
    )


def _looks_like_c(text: str) -> bool:
    return bool(re.search(r"\b(#include\s*<stdio\.h>|printf\s*\(|int\s+main\s*\()", text))


def _looks_like_ruby(text: str) -> bool:
    return bool(re.search(r"\b(def\s+\w+|puts\s+|require\s+['\"]|end\b)", text)) and "fun " not in text


def _looks_like_php(text: str) -> bool:
    return bool(
        "<?php" in text
        or re.search(r"\$\w+\s*=", text)
        or re.search(r"\b(echo\s+|namespace\s+\w+;)\b", text)
    )


def _looks_like_lua(text: str) -> bool:
    return bool(re.search(r"\b(function\s+\w+|local\s+\w+)\b", text)) and "def " not in text


def _looks_like_r(text: str) -> bool:
    return bool(re.search(r"\b(library\(|<-|cat\(|print\(|data\.frame)", text))


def _looks_like_powershell(text: str) -> bool:
    return bool(re.search(r"\b(Write-Host|Get-|Set-|param\s*\(|\$\w+:)", text))


def _looks_like_bash(text: str) -> bool:
    return bool(re.search(r"\b(echo\s+|#!/bin/(ba)?sh|fi\b|then\b)", text))


def _looks_like_scala(text: str) -> bool:
    return bool(re.search(r"\b(object\s+\w+|def\s+main|import\s+scala\.)", text))


def _looks_like_swift(text: str) -> bool:
    return bool(
        re.search(r"\bimport\s+Foundation\b", text)
        or re.search(r"\bfunc\s+\w+\([^)]*\)\s*->", text)
        or re.search(r"\bvar\s+\w+\s*:\s*\w+", text)
    )


def _looks_like_javascript(text: str) -> bool:
    return bool(
        re.search(
            r"\b(console\.log|const|let|var|=>|function|document\.|window\.|Promise|async\s+function|require\()\b",
            text,
        )
    )


def _looks_like_python(text: str) -> bool:
    return bool(
        re.search(r"^\s*#", text, re.M)
        or re.search(r"\b(def\s+\w+|import\s+\w+|from\s+\w+\s+import)\b", text)
        or re.search(r"\bprint\s*\(", text)
    ) and not re.search(r"\b(public\s+class|func\s+main|package\s+main|fn\s+main)\b", text)
