# app/services/repository_analyzer.py
from __future__ import annotations

import os
import ast
import re
import json
import sqlite3
import hashlib
import logging
from pathlib import Path
from typing import Any, Dict

from app.services.ollama import generate

logger = logging.getLogger("avatar.repository_analyzer")

# LLM Fallback prompt
REPOSITORY_ANALYZER_SYSTEM_PROMPT = """
You are Avatar's Repository Intelligence Engineer (Qwen3 8B role).
Your responsibilities:
- Inspect code style, directory structures, and file locations.
- Map out files and understand coding conventions.
- Detect framework layouts, dependency trees, and external packages.

Return ONLY a JSON object with the following keys:
  - "style_conventions": str (indentation, naming style, snake vs camel case)
  - "frameworks_detected": list[str] (list of framework names)
  - "key_dependencies": list[str] (external dependencies detected)
  - "related_files": list[str] (list of file paths that are relevant to check)
Do NOT output any markdown, code fences, or text outside the JSON block.
"""

def get_db_connection(project_id: str) -> sqlite3.Connection:
    """Get active sqlite connection for the project symbol database."""
    from app.main import BASE_DIR
    db_dir = (BASE_DIR / project_id).resolve() if project_id else BASE_DIR.resolve()
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / ".symbols.db"
    
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    
    # Initialize schema
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS symbols (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL, -- class, function, method, route, schema, var, import
                file_path TEXT NOT NULL,
                start_line INTEGER,
                end_line INTEGER,
                docstring TEXT,
                signature TEXT,
                dependencies TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS file_hashes (
                file_path TEXT PRIMARY KEY,
                hash TEXT NOT NULL,
                last_updated REAL
            )
        """)
    return conn

# =====================================================================
# SYNTAX-AWARE AST & REGEX SYMBOL EXTRACTORS
# =====================================================================
class PythonSymbolExtractor(ast.NodeVisitor):
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.symbols: list[dict] = []
        self.current_class: str | None = None

    def visit_ClassDef(self, node: ast.ClassDef):
        doc = ast.get_docstring(node) or ""
        sym_id = f"py:class:{self.file_path}:{node.name}"
        self.symbols.append({
            "id": sym_id,
            "name": node.name,
            "type": "class",
            "file_path": self.file_path,
            "start_line": node.lineno,
            "end_line": getattr(node, "end_lineno", node.lineno),
            "docstring": doc,
            "signature": f"class {node.name}",
            "dependencies": json.dumps([base.id for base in node.bases if hasattr(base, "id")])
        })
        
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        doc = ast.get_docstring(node) or ""
        args = [arg.arg for arg in node.args.args]
        sig = f"def {node.name}({', '.join(args)})"
        
        # Route detection in FastAPI
        routes = []
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and hasattr(dec.func, "attr"):
                if dec.func.attr in {"get", "post", "put", "delete", "patch", "route"}:
                    routes.append(dec.func.attr)

        sym_type = "method" if self.current_class else "function"
        if routes:
            sym_type = "route"
            
        sym_id = f"py:{sym_type}:{self.file_path}:{self.current_class or ''}:{node.name}"
        self.symbols.append({
            "id": sym_id,
            "name": node.name,
            "type": sym_type,
            "file_path": self.file_path,
            "start_line": node.lineno,
            "end_line": getattr(node, "end_lineno", node.lineno),
            "docstring": doc,
            "signature": sig,
            "dependencies": json.dumps(routes)
        })
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self.visit_FunctionDef(node)

    def visit_Import(self, node: ast.Import):
        for name in node.names:
            sym_id = f"py:import:{self.file_path}:{name.name}"
            self.symbols.append({
                "id": sym_id,
                "name": name.name,
                "type": "import",
                "file_path": self.file_path,
                "start_line": node.lineno,
                "end_line": node.lineno,
                "docstring": "",
                "signature": f"import {name.name}",
                "dependencies": "[]"
            })

    def visit_ImportFrom(self, node: ast.ImportFrom):
        mod = node.module or ""
        for name in node.names:
            sym_id = f"py:import:{self.file_path}:{mod}:{name.name}"
            self.symbols.append({
                "id": sym_id,
                "name": name.name,
                "type": "import",
                "file_path": self.file_path,
                "start_line": node.lineno,
                "end_line": node.lineno,
                "docstring": "",
                "signature": f"from {mod} import {name.name}",
                "dependencies": "[]"
            })

def parse_javascript_symbols(content: str, file_path: str) -> list[dict]:
    symbols = []
    # Simple regex matches for JS/TS classes & functions
    class_pattern = re.compile(r'class\s+([a-zA-Z0-9_]+)', re.MULTILINE)
    func_pattern = re.compile(r'(?:function|const|let)\s+([a-zA-Z0-9_]+)\s*(?:=\s*(?:async\s*)?\(.*?\)\s*=>|\(.*?\))', re.MULTILINE)
    import_pattern = re.compile(r'(?:import|require)(?:\s+.*?\s+from\s+)?\(?\s*[\'"]([^\'"]+)[\'"]', re.MULTILINE)

    for i, line in enumerate(content.splitlines(), start=1):
        if m := class_pattern.search(line):
            symbols.append({
                "id": f"js:class:{file_path}:{m.group(1)}",
                "name": m.group(1),
                "type": "class",
                "file_path": file_path,
                "start_line": i,
                "end_line": i,
                "docstring": "",
                "signature": f"class {m.group(1)}",
                "dependencies": "[]"
            })
        if m := func_pattern.search(line):
            symbols.append({
                "id": f"js:function:{file_path}:{m.group(1)}",
                "name": m.group(1),
                "type": "function",
                "file_path": file_path,
                "start_line": i,
                "end_line": i,
                "docstring": "",
                "signature": f"function {m.group(1)}",
                "dependencies": "[]"
            })
        if m := import_pattern.search(line):
            symbols.append({
                "id": f"js:import:{file_path}:{m.group(1)}",
                "name": m.group(1),
                "type": "import",
                "file_path": file_path,
                "start_line": i,
                "end_line": i,
                "docstring": "",
                "signature": line.strip(),
                "dependencies": "[]"
            })
    return symbols

def parse_sql_schemas(content: str, file_path: str) -> list[dict]:
    symbols = []
    pattern = re.compile(r'CREATE\s+TABLE\s+([a-zA-Z0-9_]+)', re.IGNORECASE)
    for i, line in enumerate(content.splitlines(), start=1):
        if m := pattern.search(line):
            symbols.append({
                "id": f"sql:schema:{file_path}:{m.group(1)}",
                "name": m.group(1),
                "type": "schema",
                "file_path": file_path,
                "start_line": i,
                "end_line": i,
                "docstring": "",
                "signature": f"TABLE {m.group(1)}",
                "dependencies": "[]"
            })
    return symbols

# =====================================================================
# INCREMENTAL SCANNER ENGINE
# =====================================================================
def index_file(project_id: str, file_path: Path) -> None:
    """Compute hash and parse file symbols if hash has changed."""
    from app.main import BASE_DIR
    proj_dir = (BASE_DIR / project_id).resolve() if project_id else BASE_DIR.resolve()
    rel_path = str(file_path.relative_to(proj_dir)).replace("\\", "/")
    
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        file_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
    except Exception as e:
        logger.error("Failed to read file for indexing %s: %s", file_path, e)
        return

    conn = get_db_connection(project_id)
    with conn:
        row = conn.execute("SELECT hash FROM file_hashes WHERE file_path = ?", (rel_path,)).fetchone()
        if row and row["hash"] == file_hash:
            # Skip parsing, file is clean
            return

        logger.info("Incremental index: parsing changed file %s", rel_path)
        
        # Parse symbols based on file extension
        extracted_symbols: list[dict] = []
        ext = file_path.suffix.lower()
        
        if ext == ".py":
            try:
                tree = ast.parse(content)
                extractor = PythonSymbolExtractor(rel_path)
                extractor.visit(tree)
                extracted_symbols = extractor.symbols
            except Exception as ast_err:
                logger.warning("AST parse failed for %s: %s", rel_path, ast_err)
        elif ext in {".js", ".jsx", ".ts", ".tsx"}:
            extracted_symbols = parse_javascript_symbols(content, rel_path)
        elif ext == ".sql":
            extracted_symbols = parse_sql_schemas(content, rel_path)

        # Update Database
        conn.execute("DELETE FROM symbols WHERE file_path = ?", (rel_path,))
        for sym in extracted_symbols:
            conn.execute("""
                INSERT OR REPLACE INTO symbols (id, name, type, file_path, start_line, end_line, docstring, signature, dependencies)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (sym["id"], sym["name"], sym["type"], sym["file_path"], sym["start_line"], sym["end_line"], sym["docstring"], sym["signature"], sym["dependencies"]))

        conn.execute("""
            INSERT OR REPLACE INTO file_hashes (file_path, hash, last_updated)
            VALUES (?, ?, ?)
        """, (rel_path, file_hash, os.path.getmtime(str(file_path))))

def run_project_incremental_indexing(project_id: str) -> None:
    """Identify all workspace files and perform incremental indexes."""
    from app.main import BASE_DIR
    proj_dir = (BASE_DIR / project_id).resolve() if project_id else BASE_DIR.resolve()
    
    ignored_patterns = {
        "node_modules", ".venv", "venv", "dist", "build", ".cache", 
        "coverage", ".git", "__pycache__", ".symbols.db"
    }

    for root, dirs, files in os.walk(str(proj_dir)):
        # Filter directories inplace to skip scanning them
        dirs[:] = [d for d in dirs if d not in ignored_patterns]
        for f in files:
            file_path = Path(root) / f
            index_file(project_id, file_path)

# =====================================================================
# DEPENDENCY GRAPH RESOLUTIONS
# =====================================================================
def get_dependents(project_id: str, file_path: str) -> list[str]:
    """Find files that import/depend on the specified target file."""
    conn = get_db_connection(project_id)
    dependents = set()
    
    # Extract file base name to check for imports
    target_base = Path(file_path).stem
    
    with conn:
        rows = conn.execute("SELECT file_path, signature FROM symbols WHERE type = 'import'").fetchall()
        for r in rows:
            sig = r["signature"].lower()
            if target_base.lower() in sig:
                dependents.add(r["file_path"])
    return list(dependents)

# =====================================================================
# CHANGE IMPACT ANALYZER
# =====================================================================
def analyze_change_impact(project_id: str, file_changes: list[dict]) -> dict:
    """Predict breakages and list affected dependents based on proposed edits."""
    impact_report = {
        "affected_modules": [],
        "warnings": [],
        "related_tests": []
    }
    
    conn = get_db_connection(project_id)
    for change in file_changes:
        path = change.get("path")
        if not path:
            continue
            
        deps = get_dependents(project_id, path)
        impact_report["affected_modules"].extend(deps)
        
        # Scan if there's any signature break
        # (e.g. if we remove or alter parameters, we query symbols database)
        rows = conn.execute("SELECT name, signature FROM symbols WHERE file_path = ? AND type = 'function'", (path,)).fetchall()
        for r in rows:
            name = r["name"]
            # Look up if function was deleted or altered in proposed new text
            new_content = change.get("content")
            if new_content and name not in new_content:
                impact_report["warnings"].append(
                    f"Warning: Symbol '{name}' in '{path}' seems removed or renamed. "
                    f"Dependents {[str(d) for d in deps]} might be broken."
                )

        # Identify tests importing this file
        with conn:
            test_rows = conn.execute("SELECT DISTINCT file_path FROM symbols WHERE file_path LIKE 'test_%' OR file_path LIKE '%_test%'").fetchall()
            for tr in test_rows:
                test_path = tr["file_path"]
                # If test path imports or is close in naming
                if Path(path).stem.lower() in test_path.lower():
                    impact_report["related_tests"].append(test_path)
                    
    impact_report["affected_modules"] = list(set(impact_report["affected_modules"]))
    impact_report["related_tests"] = list(set(impact_report["related_tests"]))
    return impact_report

# =====================================================================
# SYMBOL LOOKUP & SEARCH
# =====================================================================
def lookup_symbol(project_id: str, query: str) -> list[dict]:
    """Instant search in symbol database for matching classes, functions, or schemas."""
    conn = get_db_connection(project_id)
    results = []
    with conn:
        rows = conn.execute("""
            SELECT name, type, file_path, start_line, signature, docstring 
            FROM symbols 
            WHERE name LIKE ? OR docstring LIKE ?
            LIMIT 20
        """, (f"%{query}%", f"%{query}%")).fetchall()
        for r in rows:
            results.append(dict(r))
    return results

# =====================================================================
# OVERALL CONVENTION ANALYZER
# =====================================================================
async def analyze_repository_structure(project_id: str, context_files: list[str]) -> Dict[str, Any]:
    """Inspect conventions and scan repository structures."""
    # Ensure incremental indexing completes
    run_project_incremental_indexing(project_id)

    prompt = json.dumps({
        "project_id": project_id,
        "scanned_files": context_files,
    }, indent=2)
    raw, ok = await generate(
        model="Avatar coding model",
        prompt=prompt,
        system=REPOSITORY_ANALYZER_SYSTEM_PROMPT,
        role="reviewer",
    )
    if not ok:
        logger.error("Repository Analyzer LLM unavailable")
        return {"error": "Repository Analyzer unavailable"}
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        res = json.loads(raw[start:end])
        # Append symbol stats to result
        conn = get_db_connection(project_id)
        with conn:
            sym_count = conn.execute("SELECT count(*) as count FROM symbols").fetchone()["count"]
            res["indexed_symbols_count"] = sym_count
        return res
    except Exception as e:
        logger.exception("Failed to parse repository analyzer output: %s", e)
        return {"error": f"Parse error: {e}"}
