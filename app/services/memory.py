import sqlite3
import json
from pathlib import Path

# Path to the SQLite database file for project memory
MEMORY_DB = Path(__file__).resolve().parent.parent / "project_memory.db"


def _init_db() -> None:
    """Initialize the memory database with the required table if it does not exist."""
    conn = sqlite3.connect(MEMORY_DB)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS memory (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()

# Ensure the database and table are ready on import
_init_db()


def _make_key(project_id: str, suffix: str) -> str:
    """Create a namespaced key for a given project.

    Args:
        project_id: Unique identifier for the project (e.g., a UUID or name).
        suffix: The specific memory entry type such as 'requirements', 'plan', etc.

    Returns:
        A string in the form "{project_id}:{suffix}".
    """
    return f"{project_id}:{suffix}"


# Generic key‑value helpers ---------------------------------------------------

def set_memory(key: str, value: str) -> None:
    """Store or overwrite a value for a given key in the memory database."""
    conn = sqlite3.connect(MEMORY_DB)
    cursor = conn.cursor()
    cursor.execute(
        "REPLACE INTO memory (key, value) VALUES (?, ?)", (key, value)
    )
    conn.commit()
    conn.close()


def get_memory(key: str) -> str | None:
    """Retrieve a stored value for a given key.

    Returns ``None`` if the key does not exist.
    """
    conn = sqlite3.connect(MEMORY_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM memory WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def get_all_memory() -> dict:
    """Return the entire memory store as a dictionary of ``key -> value`` pairs."""
    conn = sqlite3.connect(MEMORY_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM memory")
    rows = cursor.fetchall()
    conn.close()
    return {k: v for k, v in rows}


# Project‑scoped helpers ---------------------------------------------------

def set_requirements(project_id: str, data: dict) -> None:
    """Persist the requirements JSON for a specific project."""
    set_memory(_make_key(project_id, "requirements"), json.dumps(data))


def get_requirements(project_id: str) -> dict:
    """Retrieve the stored requirements for a project, returning an empty dict if none exist."""
    raw = get_memory(_make_key(project_id, "requirements"))
    return json.loads(raw) if raw else {}


def set_plan(project_id: str, data: dict) -> None:
    """Persist the planning JSON for a specific project."""
    set_memory(_make_key(project_id, "plan"), json.dumps(data))


def get_plan(project_id: str) -> dict:
    """Retrieve the stored plan for a project, returning an empty dict if none exist."""
    raw = get_memory(_make_key(project_id, "plan"))
    return json.loads(raw) if raw else {}


def store_review(project_id: str, data: dict) -> None:
    """Store the review results for a project."""
    set_memory(_make_key(project_id, "review"), json.dumps(data))


def get_review(project_id: str) -> dict:
    """Retrieve the stored review for a project, returning an empty dict if none exist."""
    raw = get_memory(_make_key(project_id, "review"))
    return json.loads(raw) if raw else {}
