from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.services.diagnostics import Diagnostic, ToolStatus


def _run(command: list[str], code: str, suffix: str) -> tuple[str, str, bool]:
    executable = _find_executable(command[0])
    if not executable:
        return "", f"{command[0]} is not installed.", False

    with tempfile.TemporaryDirectory(prefix="avatar-analysis-") as tmp:
        path = Path(tmp) / f"snippet{suffix}"
        path.write_text(code, encoding="utf-8")
        full_command = [executable, *command[1:], str(path)]
        result = subprocess.run(full_command, text=True, capture_output=True, timeout=20, check=False)
        return result.stdout + result.stderr, "", True


def _find_executable(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found

    root = Path(__file__).resolve().parents[2]
    import os
    if os.name == 'nt':
        candidates = [
            root / "node_modules" / ".bin" / f"{name}.cmd",
            root / "node_modules" / ".bin" / name,
        ]
    else:
        candidates = [
            root / "node_modules" / ".bin" / name,
            root / "node_modules" / ".bin" / f"{name}.cmd",
        ]
        
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def run_python_tools(code: str) -> tuple[list[Diagnostic], list[ToolStatus]]:
    diagnostics: list[Diagnostic] = []
    statuses: list[ToolStatus] = []

    pyflakes_out, pyflakes_msg, pyflakes_ok = _run(["pyflakes"], code, ".py")
    statuses.append(ToolStatus("pyflakes", pyflakes_ok, pyflakes_msg))
    if pyflakes_ok:
        diagnostics.extend(_parse_colon_output(pyflakes_out, "pyflakes", "style"))

    pylint_out, pylint_msg, pylint_ok = _run(["pylint", "--output-format=json", "--score=n"], code, ".py")
    statuses.append(ToolStatus("pylint", pylint_ok, pylint_msg))
    if pylint_ok:
        try:
            for item in json.loads(pylint_out or "[]"):
                diagnostics.append(
                    Diagnostic(
                        title=item.get("symbol", "pylint finding").replace("-", " ").title(),
                        severity=_pylint_severity(item.get("type", "")),
                        category="style" if item.get("type") in {"convention", "refactor"} else "logic",
                        detail=item.get("message", ""),
                        line=item.get("line") or 1,
                        column=(item.get("column") or 0) + 1,
                        section=f"line {item.get('line') or 1}",
                        source="pylint",
                        fix_hint="Review the pylint diagnostic and simplify or correct the affected code.",
                    )
                )
        except Exception:
            diagnostics.extend(_parse_colon_output(pylint_out, "pylint", "logic"))

    bandit_out, bandit_msg, bandit_ok = _run(["bandit", "-q", "-f", "json"], code, ".py")
    statuses.append(ToolStatus("bandit", bandit_ok, bandit_msg))
    if bandit_ok:
        try:
            for item in json.loads(bandit_out or "{}").get("results", []):
                diagnostics.append(
                    Diagnostic(
                        title=item.get("test_name", "Bandit security finding"),
                        severity=_bandit_severity(item.get("issue_severity", "")),
                        category="security",
                        detail=item.get("issue_text", ""),
                        line=item.get("line_number") or 1,
                        column=1,
                        section=f"line {item.get('line_number') or 1}",
                        source="bandit",
                        fix_hint="Replace the unsafe construct with a validated, least-privilege alternative.",
                    )
                )
        except Exception:
            diagnostics.extend(_parse_colon_output(bandit_out, "bandit", "security"))

    return diagnostics, statuses


def run_node_tools(code: str, language: str) -> tuple[list[Diagnostic], list[ToolStatus]]:
    diagnostics: list[Diagnostic] = []
    statuses: list[ToolStatus] = []
    suffix = {
        "javascript": ".js",
        "typescript": ".ts",
        "html": ".html",
        "css": ".css",
        "json": ".json",
    }.get(language, ".txt")

    tools = []
    if language in {"javascript", "typescript"}:
        tools.append(("eslint", ["eslint", "--format", "json"], "logic"))
        tools.append(("prettier", ["prettier", "--check"], "style"))
    elif language == "html":
        tools.append(("htmlhint", ["htmlhint", "--format", "json"], "style"))
    elif language == "css":
        tools.append(("stylelint", ["stylelint", "--formatter", "json"], "style"))
    elif language == "json":
        try:
            json.loads(code)
        except json.JSONDecodeError as exc:
            diagnostics.append(
                Diagnostic(
                    "Invalid JSON",
                    "high",
                    "syntax",
                    exc.msg,
                    exc.lineno,
                    exc.colno,
                    section=f"line {exc.lineno}",
                    source="json",
                    fix_hint="Correct the JSON token at the reported line and column.",
                )
            )

    for name, command, category in tools:
        output, message, ok = _run(command, code, suffix)
        statuses.append(ToolStatus(name, ok, message))
        if not ok:
            continue
        diagnostics.extend(_parse_json_or_text(output, name, category))

    return diagnostics, statuses


def _parse_json_or_text(output: str, source: str, category: str) -> list[Diagnostic]:
    try:
        parsed = json.loads(output or "[]")
        items = parsed if isinstance(parsed, list) else [parsed]
        diagnostics: list[Diagnostic] = []
        for report in items:
            for message in report.get("messages", []) or report.get("warnings", []):
                diagnostics.append(
                    Diagnostic(
                        title=message.get("ruleId") or message.get("rule") or f"{source} finding",
                        severity="high" if message.get("severity") == 2 else "medium",
                        category=category,
                        detail=message.get("message", ""),
                        line=message.get("line") or 1,
                        column=message.get("column") or 1,
                        section=f"line {message.get('line') or 1}",
                        source=source,
                        fix_hint="Apply the linter suggestion while preserving behavior.",
                    )
                )
        return diagnostics
    except Exception:
        return _parse_colon_output(output, source, category)


def _parse_colon_output(output: str, source: str, category: str) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for line in output.splitlines():
        parts = line.split(":", 3)
        if len(parts) < 4:
            continue
        try:
            line_no = int(parts[1])
            column = int(parts[2])
        except ValueError:
            continue
        diagnostics.append(
            Diagnostic(
                title=f"{source} finding",
                severity="medium",
                category=category,
                detail=parts[3].strip(),
                line=line_no,
                column=column,
                section=f"line {line_no}",
                source=source,
            )
        )
    return diagnostics


def _pylint_severity(kind: str) -> str:
    return {"fatal": "critical", "error": "high", "warning": "medium", "refactor": "low", "convention": "low"}.get(kind, "medium")


def _bandit_severity(kind: str) -> str:
    return {"HIGH": "critical", "MEDIUM": "high", "LOW": "medium"}.get(kind, "medium")
