from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import HTTPException

logger = logging.getLogger("avatar.file_manager")

# Whitelisted extensions for security – removed to allow all file types (IDE supports all languages)
WHITELIST_EXTENSIONS = set()

# Maximum allowed file size (bytes). Default 5 MiB.
MAX_FILE_SIZE = 5 * 1024 * 1024

def _workspace_base() -> Path:
    """Return the base directory where all projects live.
    Imported lazily to avoid circular imports with app.main.
    """
    from app.main import BASE_DIR
    return BASE_DIR

def _resolve_path(project_id: str, rel_path: str) -> Path:
    """Resolve a relative path within a project workspace.
    Ensures the path stays inside the workspace and performs symlink checks.
    """
    if not rel_path or Path(rel_path).is_absolute():
        raise HTTPException(status_code=400, detail="Invalid file path")

    base = (_workspace_base() / project_id).resolve()
    target = (base / rel_path).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        logger.error("Path traversal attempt: %s", rel_path)
        raise HTTPException(status_code=400, detail="Invalid file path - outside of workspace")

    if target.is_symlink():
        real = target.resolve()
        try:
            real.relative_to(base)
        except ValueError:
            logger.error("Symlink points outside workspace: %s -> %s", target, real)
            raise HTTPException(status_code=400, detail="Symlink points outside of workspace")
    return target

def _validate_extension(path: Path) -> None:
    if WHITELIST_EXTENSIONS and path.suffix.lower() not in WHITELIST_EXTENSIONS:
        logger.error("Disallowed file extension: %s", path.suffix)
        raise HTTPException(status_code=400, detail=f"File extension {path.suffix} is not allowed")

def _validate_size(content: str) -> None:
    if len(content.encode("utf-8")) > MAX_FILE_SIZE:
        logger.error("File size exceeds limit (%d bytes)", len(content.encode("utf-8")))
        raise HTTPException(status_code=400, detail="File size exceeds the maximum allowed limit")

def secure_write_file(project_id: str, relative_path: str, content: str) -> None:
    """Write `content` to `relative_path` inside the project's workspace safely.
    Raises HTTPException on validation failures.
    """
    target = _resolve_path(project_id, relative_path)
    _validate_extension(target)
    _validate_size(content)
    # Ensure parent directories exist
    target.parent.mkdir(parents=True, exist_ok=True)
    # Write the file atomically – write to temp then replace
    temp_path = target.with_suffix(target.suffix + ".tmp")
    temp_path.write_text(content, encoding="utf-8")
    os.replace(temp_path, target)
    logger.info("Securely wrote file %s (project %s)", target, project_id)
