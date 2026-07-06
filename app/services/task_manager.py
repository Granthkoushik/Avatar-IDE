from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional
import json

logger = logging.getLogger("avatar.task_manager")

# Each project gets its own SQLite DB located at projects/<project_id>/tasks.db

def _db_path(project_id: str) -> Path:
    """Return the absolute path to the task database for a project."""
    from app.main import BASE_DIR
    if not project_id:
        return BASE_DIR / "tasks.db"
    return BASE_DIR / project_id / "tasks.db"

def _ensure_db(project_id: str) -> None:
    """Create the tasks DB and schema if it does not exist."""
    db_file = _db_path(project_id)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_file)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                stage TEXT NOT NULL DEFAULT 'pending',
                status TEXT NOT NULL CHECK (status IN ('pending','in_progress','completed','failed')),
                payload TEXT,
                iteration INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Migrate columns if they are missing
        columns = [
            ("progress", "INTEGER DEFAULT 0"),
            ("current_agent", "TEXT DEFAULT 'Planner'"),
            ("current_file", "TEXT DEFAULT ''"),
            ("current_command", "TEXT DEFAULT ''"),
            ("retry_count", "INTEGER DEFAULT 0"),
            ("paused", "INTEGER DEFAULT 0"),
            ("subtasks", "TEXT DEFAULT '[]'"),
            ("elapsed_time", "REAL DEFAULT 0.0"),
            ("estimated_remaining_time", "TEXT DEFAULT 'calculating...'"),
            ("eta", "TEXT DEFAULT 'N/A'")
        ]
        for col_name, col_type in columns:
            try:
                conn.execute(f"ALTER TABLE tasks ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                pass # Already exists
        conn.commit()
    finally:
        conn.close()

def create_task(project_id: str, name: str, payload: Optional[Dict] = None) -> int:
    """Insert a new task and return its ID.
    ``payload`` is stored as JSON text and will include ``project_id``.
    """
    _ensure_db(project_id)
    payload = payload or {}
    payload["project_id"] = project_id
    db_file = _db_path(project_id)
    conn = sqlite3.connect(db_file)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO tasks (name, status, payload) VALUES (?, ?, ?)",
            (name, "pending", json.dumps(payload)),
        )
        task_id = cur.lastrowid
        conn.commit()
        logger.info("Created task %s (id=%s) for project %s", name, task_id, project_id)
        return task_id
    finally:
        conn.close()

def update_task_status(project_id: str, task_id: int, status: str) -> None:
    """Update the status of a task. Allowed statuses: pending, in_progress, completed, failed."""
    if status not in {"pending", "in_progress", "completed", "failed"}:
        raise ValueError(f"Invalid status: {status}")
    _ensure_db(project_id)
    db_file = _db_path(project_id)
    conn = sqlite3.connect(db_file)
    try:
        conn.execute(
            "UPDATE tasks SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, task_id),
        )
        conn.commit()
        logger.debug("Task %s status updated to %s for project %s", task_id, status, project_id)
    finally:
        conn.close()

def update_task_progress(
    project_id: str,
    task_id: int,
    progress: int | None = None,
    current_agent: str | None = None,
    current_file: str | None = None,
    current_command: str | None = None,
    retry_count: int | None = None,
    paused: bool | None = None,
    subtasks: list | None = None,
    elapsed_time: float | None = None,
    estimated_remaining_time: str | None = None,
    status: str | None = None,
    eta: str | None = None
) -> None:
    """Dynamically update any set of progress metrics for a task."""
    _ensure_db(project_id)
    db_file = _db_path(project_id)
    conn = sqlite3.connect(db_file)
    try:
        cur = conn.cursor()
        updates = []
        params = []
        if progress is not None:
            updates.append("progress = ?")
            params.append(progress)
        if current_agent is not None:
            updates.append("current_agent = ?")
            params.append(current_agent)
        if current_file is not None:
            updates.append("current_file = ?")
            params.append(current_file)
        if current_command is not None:
            updates.append("current_command = ?")
            params.append(current_command)
        if retry_count is not None:
            updates.append("retry_count = ?")
            params.append(retry_count)
        if paused is not None:
            updates.append("paused = ?")
            params.append(1 if paused else 0)
        if subtasks is not None:
            updates.append("subtasks = ?")
            params.append(json.dumps(subtasks))
        if elapsed_time is not None:
            updates.append("elapsed_time = ?")
            params.append(elapsed_time)
        if estimated_remaining_time is not None:
            updates.append("estimated_remaining_time = ?")
            params.append(estimated_remaining_time)
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if eta is not None:
            updates.append("eta = ?")
            params.append(eta)
            
        if updates:
            query = f"UPDATE tasks SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
            params.append(task_id)
            cur.execute(query, tuple(params))
            conn.commit()
    finally:
        conn.close()

def _row_to_task(row) -> dict:
    return {
        "id": row[0],
        "name": row[1],
        "status": row[2],
        "payload": json.loads(row[3]) if row[3] else None,
        "created_at": row[4],
        "updated_at": row[5],
        "progress": row[6],
        "current_agent": row[7],
        "current_file": row[8],
        "current_command": row[9],
        "retry_count": row[10],
        "paused": bool(row[11]),
        "subtasks": json.loads(row[12]) if row[12] else [],
        "elapsed_time": row[13],
        "estimated_remaining_time": row[14],
        "eta": row[15] if len(row) > 15 else "N/A"
    }

def get_task(project_id: str, task_id: int) -> Optional[Dict]:
    """Retrieve a single task as a dict, or ``None`` if not found."""
    _ensure_db(project_id)
    db_file = _db_path(project_id)
    conn = sqlite3.connect(db_file)
    try:
        cur = conn.cursor()
        cur.execute(
            """
             SELECT id, name, status, payload, created_at, updated_at,
                    progress, current_agent, current_file, current_command,
                    retry_count, paused, subtasks, elapsed_time, estimated_remaining_time, eta
             FROM tasks WHERE id = ?
            """,
            (task_id,)
        )
        row = cur.fetchone()
        if not row:
            return None
        return _row_to_task(row)
    finally:
        conn.close()

def list_pending_tasks(project_id: str) -> List[Dict]:
    """Return all tasks with status ``pending`` for the given project."""
    _ensure_db(project_id)
    db_file = _db_path(project_id)
    conn = sqlite3.connect(db_file)
    try:
        cur = conn.cursor()
        cur.execute(
            """
             SELECT id, name, status, payload, created_at, updated_at,
                    progress, current_agent, current_file, current_command,
                    retry_count, paused, subtasks, elapsed_time, estimated_remaining_time, eta
             FROM tasks WHERE status = 'pending' ORDER BY created_at
            """
        )
        rows = cur.fetchall()
        return [_row_to_task(row) for row in rows]
    finally:
        conn.close()


def list_all_tasks(project_id: str) -> List[Dict]:
    """Return all tasks ordered by created_at DESC."""
    _ensure_db(project_id)
    db_file = _db_path(project_id)
    conn = sqlite3.connect(db_file)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, name, status, payload, created_at, updated_at,
                   progress, current_agent, current_file, current_command,
                   retry_count, paused, subtasks, elapsed_time, estimated_remaining_time, eta
            FROM tasks ORDER BY created_at DESC
            """
        )
        rows = cur.fetchall()
        return [_row_to_task(row) for row in rows]
    finally:
        conn.close()
