"""Quick test for auto_namer module."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.auto_namer import infer_filename, sanitize_path

tests = [
    ("SQL schema", "CREATE TABLE users (id INT, name TEXT, email TEXT);", "schema.sql"),
    ("Express server", "import express\nconst app = express()\napp.get('/', (req,res)=>res.send('hi'))\napp.listen(3000)", "server.js"),
    ("Python class", "class AuthManager:\n    def login(self, user, pw):\n        return True", "auth_manager.py"),
    ("HTML file", "<!DOCTYPE html>\n<html><head><title>App</title></head><body></body></html>", "index.html"),
    ("SQLite import", "import sqlite3\nconn = sqlite3.connect('db.sqlite3')\ncursor = conn.cursor()", "database.py"),
    ("sanitize untitled", None, "database.py"),  # special case
    ("FastAPI main", "from fastapi import FastAPI\napp = FastAPI()\nif __name__ == '__main__':\n    import uvicorn\n    uvicorn.run(app)", "main.py"),
]

passed = 0
failed = 0
for name, content, expected in tests:
    if name == "sanitize untitled":
        result = sanitize_path("untitled.py", "import sqlite3\nconn = sqlite3.connect('db.sqlite3')")
    else:
        result = infer_filename(content)
    
    ok = result == expected
    status = "✅" if ok else "❌"
    print(f"{status} {name}: got '{result}' (expected '{expected}')")
    if ok:
        passed += 1
    else:
        failed += 1

print(f"\n{passed} passed, {failed} failed")
