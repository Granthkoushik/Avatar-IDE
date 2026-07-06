from fastapi import APIRouter
import sqlite3
from pathlib import Path

router = APIRouter()
DB_PATH = Path(__file__).parent.parent / "study_planner.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            due TEXT,
            completed INTEGER NOT NULL DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@router.get("/api/planner/tasks")
async def get_tasks():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, title, due, completed FROM tasks')
    rows = c.fetchall()
    conn.close()
    tasks = [{"id": r[0], "title": r[1], "due": r[2], "completed": bool(r[3])} for r in rows]
    return {"tasks": tasks}

@router.post("/api/planner/tasks")
async def create_task(task: dict):
    title = task.get("title")
    due = task.get("due")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO tasks (title, due, completed) VALUES (?, ?, 0)', (title, due))
    conn.commit()
    task_id = c.lastrowid
    conn.close()
    return {"id": task_id, "title": title, "due": due, "completed": False}

@router.put("/api/planner/tasks/{task_id}")
async def update_task(task_id: int, data: dict):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if "title" in data:
        c.execute('UPDATE tasks SET title = ? WHERE id = ?', (data["title"], task_id))
    if "due" in data:
        c.execute('UPDATE tasks SET due = ? WHERE id = ?', (data["due"], task_id))
    if "completed" in data:
        completed = 1 if data["completed"] else 0
        c.execute('UPDATE tasks SET completed = ? WHERE id = ?', (completed, task_id))
    conn.commit()
    conn.close()
    return {"id": task_id, **data}

@router.delete("/api/planner/tasks/{task_id}")
async def delete_task(task_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()
    return {"deleted": task_id}
