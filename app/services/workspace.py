# app/services/workspace.py
from __future__ import annotations

import os
import logging
import shutil
from pathlib import Path
from app.services.file_manager import secure_write_file, _resolve_path
from app.services.validation import validate_path

logger = logging.getLogger("avatar.workspace")

# --- Execution Mode State ---
_EXECUTION_MODE = "autonomous"

def get_execution_mode() -> str:
    global _EXECUTION_MODE
    return _EXECUTION_MODE

def set_execution_mode(mode: str) -> None:
    global _EXECUTION_MODE
    if mode in {"autonomous", "review", "read_only"}:
        _EXECUTION_MODE = mode
        logger.info("Workspace execution mode set to: %s", mode)


# --- Undo / Redo Manager ---
class UndoRedoManager:
    def __init__(self):
        self.undo_stack: list[tuple[str, str | None, str | None]] = []
        self.redo_stack: list[tuple[str, str | None, str | None]] = []

    def record_change(self, filepath: str, old_content: str | None, new_content: str | None):
        """Record a file state change. None signifies non-existence."""
        self.undo_stack.append((filepath, old_content, new_content))
        self.redo_stack.clear()

    def undo(self, project_id: str = "") -> dict:
        if not self.undo_stack:
            return {"success": False, "message": "Nothing to undo"}
        
        filepath, old_content, new_content = self.undo_stack.pop()
        self.redo_stack.append((filepath, old_content, new_content))
        
        from app.main import BASE_DIR
        target = (_resolve_path(project_id, filepath) if project_id else BASE_DIR / filepath).resolve()
        
        if old_content is None:
            if target.exists():
                target.unlink()
            logger.info("Undo: deleted file %s", filepath)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(old_content, encoding="utf-8")
            logger.info("Undo: restored file %s", filepath)
            
        return {"success": True, "filepath": filepath}

    def redo(self, project_id: str = "") -> dict:
        if not self.redo_stack:
            return {"success": False, "message": "Nothing to redo"}
            
        filepath, old_content, new_content = self.redo_stack.pop()
        self.undo_stack.append((filepath, old_content, new_content))
        
        from app.main import BASE_DIR
        target = (_resolve_path(project_id, filepath) if project_id else BASE_DIR / filepath).resolve()
        
        if new_content is None:
            if target.exists():
                target.unlink()
            logger.info("Redo: deleted file %s", filepath)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(new_content, encoding="utf-8")
            logger.info("Redo: wrote file %s", filepath)
            
        return {"success": True, "filepath": filepath}

history_manager = UndoRedoManager()


# --- Workspace Manager ---
class WorkspaceManager:
    """Manages file reading, writing, renaming, deleting, and history logs."""
    
    def __init__(self, project_id: str):
        self.project_id = project_id
        from app.main import BASE_DIR
        self.base_dir = (BASE_DIR / project_id).resolve() if project_id else BASE_DIR.resolve()

    def get_absolute_path(self, relative_path: str) -> Path:
        safe_rel = validate_path(relative_path)
        return _resolve_path(self.project_id, safe_rel)

    def write_file(self, relative_path: str, content: str) -> None:
        if get_execution_mode() == "read_only":
            logger.warning("Attempted to write file %s in read_only mode – skipped", relative_path)
            return

        target = self.get_absolute_path(relative_path)
        old_content = None
        if target.exists() and not target.is_dir():
            try:
                old_content = target.read_text(encoding="utf-8")
            except Exception:
                pass
                
        secure_write_file(self.project_id, relative_path, content)
        history_manager.record_change(relative_path, old_content, content)

    def create_file(self, relative_path: str) -> None:
        if get_execution_mode() == "read_only":
            logger.warning("Attempted to create file %s in read_only mode – skipped", relative_path)
            return

        target = self.get_absolute_path(relative_path)
        if target.exists():
            return
            
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("", encoding="utf-8")
        history_manager.record_change(relative_path, None, "")
        logger.info("Created file: %s", relative_path)

    def delete_file(self, relative_path: str) -> None:
        if get_execution_mode() == "read_only":
            logger.warning("Attempted to delete file %s in read_only mode – skipped", relative_path)
            return

        target = self.get_absolute_path(relative_path)
        if not target.exists():
            return
            
        old_content = None
        if not target.is_dir():
            try:
                old_content = target.read_text(encoding="utf-8")
                target.unlink()
            except Exception as e:
                logger.error("Failed to delete file %s: %s", relative_path, e)
        else:
            try:
                shutil.rmtree(target)
            except Exception as e:
                logger.error("Failed to delete directory %s: %s", relative_path, e)

        history_manager.record_change(relative_path, old_content, None)
        logger.info("Deleted: %s", relative_path)

    def rename_file(self, old_rel: str, new_rel: str) -> None:
        if get_execution_mode() == "read_only":
            logger.warning("Attempted to rename %s to %s in read_only mode – skipped", old_rel, new_rel)
            return

        old_target = self.get_absolute_path(old_rel)
        new_target = self.get_absolute_path(new_rel)
        
        if not old_target.exists():
            raise FileNotFoundError(f"Source file not found: {old_rel}")
            
        old_content = None
        if not old_target.is_dir():
            old_content = old_target.read_text(encoding="utf-8")
            
        new_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_target), str(new_target))
        
        # Record as delete of old and write of new
        history_manager.record_change(old_rel, old_content, None)
        history_manager.record_change(new_rel, None, old_content)
        logger.info("Renamed/Moved: %s -> %s", old_rel, new_rel)

    def read_file(self, relative_path: str) -> str:
        target = self.get_absolute_path(relative_path)
        if not target.exists() or target.is_dir():
            raise FileNotFoundError(f"File not found: {relative_path}")
        return target.read_text(encoding="utf-8")

    def create_directory(self, relative_path: str) -> None:
        if get_execution_mode() == "read_only":
            return
        target = self.get_absolute_path(relative_path)
        target.mkdir(parents=True, exist_ok=True)
        logger.info("Created folder: %s", relative_path)

    def list_files(self) -> list[str]:
        all_files = []
        ignore_dirs = {".venv", "node_modules", ".git", "__pycache__", ".idea", ".vscode"}
        for root, dirs, files in os.walk(self.base_dir):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            for f in files:
                if f.endswith((".pyc", ".pyo", ".exe", ".dll", ".so", ".dylib", ".db", ".sqlite3")):
                    continue
                path = Path(root) / f
                rel_path = path.relative_to(self.base_dir).as_posix()
                all_files.append(rel_path)
        return all_files
