from __future__ import annotations

from dataclasses import dataclass, field


SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}
VALID_CATEGORIES = {"syntax", "runtime", "security", "performance", "logic", "style", "maintainability", "quality"}


@dataclass
class Diagnostic:
    title: str
    severity: str
    category: str
    detail: str
    line: int = 1
    column: int = 1
    end_line: int | None = None
    end_column: int | None = None
    section: str = "general"
    source: str = "avatar"
    fix_hint: str = ""

    def to_dict(self) -> dict:
        severity = self.severity.lower()
        category = self.category.lower()
        return {
            "title": self.title,
            "severity": severity if severity in SEVERITY_ORDER else "medium",
            "category": category if category in VALID_CATEGORIES else "quality",
            "section": self.section or f"line {self.line}",
            "detail": self.detail,
            "line": max(1, int(self.line or 1)),
            "column": max(1, int(self.column or 1)),
            "end_line": self.end_line or self.line,
            "end_column": self.end_column or max(2, self.column + 1),
            "source": self.source,
            "fix_hint": self.fix_hint,
        }


@dataclass
class ToolStatus:
    name: str
    available: bool
    message: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "available": self.available, "message": self.message}


@dataclass
class AnalysisContext:
    code: str
    language: str
    diagnostics: list[Diagnostic] = field(default_factory=list)
    tool_status: list[ToolStatus] = field(default_factory=list)
    pipeline: list[str] = field(default_factory=list)

    def add(self, diagnostic: Diagnostic) -> None:
        self.diagnostics.append(diagnostic)

    def stage(self, message: str) -> None:
        self.pipeline.append(message)


def dedupe_diagnostics(diagnostics: list[Diagnostic]) -> list[Diagnostic]:
    seen: set[tuple] = set()
    unique: list[Diagnostic] = []
    for item in diagnostics:
        key = (item.title.lower(), item.line, item.column, item.category.lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def estimate_fix_time(issue_count: int, code: str) -> str:
    seconds = max(30, issue_count * 32 + len(code.splitlines()) * 2)
    minutes, remaining = divmod(seconds, 60)
    return f"~{minutes}m {remaining:02d}s" if minutes else f"~{remaining}s"


def overall_severity(issues: list[dict]) -> str:
    if not issues:
        return "low"
    return max(issues, key=lambda issue: SEVERITY_ORDER.get(issue.get("severity", "low"), 0)).get("severity", "medium")
