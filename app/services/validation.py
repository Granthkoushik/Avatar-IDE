from __future__ import annotations

import re
from pathlib import PurePosixPath

from fastapi import HTTPException

_WINDOWS_DRIVE_RE = re.compile(r"^[a-zA-Z]:")
_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def validate_path(path: str) -> str:
    """Validate and normalize a workspace-relative path."""
    normalized = path.replace("\\", "/").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Invalid path: empty path")
    if normalized.startswith("/") or _WINDOWS_DRIVE_RE.match(normalized):
        raise HTTPException(status_code=400, detail="Invalid path: absolute paths are not allowed")

    parts = PurePosixPath(normalized).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise HTTPException(status_code=400, detail="Invalid path: traversal is not allowed")
    if any(part.upper().split(".")[0] in _RESERVED_NAMES for part in parts):
        raise HTTPException(status_code=400, detail="Invalid path: reserved filename")

    return "/".join(parts)
