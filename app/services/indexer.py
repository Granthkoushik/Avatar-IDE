from __future__ import annotations

import ast
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger("avatar.indexer")

class ProjectIndex:
    def __init__(self, root_dir: Path):
        self.root_dir = Path(root_dir).resolve()
        self.files: dict[str, dict] = {}
        self.dependencies: list[str] = []
        self.frameworks: set[str] = set()
        self.import_graph: dict[str, list[str]] = {}

    def scan(self) -> None:
        """Scan the entire workspace directory and build semantic indexes."""
        self.files.clear()
        self.dependencies.clear()
        self.frameworks.clear()
        self.import_graph.clear()

        ignore_dirs = {".venv", "node_modules", ".git", "__pycache__", "build", "dist", ".ruff_cache"}
        for root, dirs, filenames in os.walk(self.root_dir):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            for name in filenames:
                path = Path(root) / name
                if path.suffix.lower() in {".pyc", ".pyo", ".exe", ".dll", ".so", ".dylib", ".db", ".sqlite3"}:
                    continue
                rel_path = path.relative_to(self.root_dir).as_posix()
                try:
                    self.index_file(path, rel_path)
                except Exception as e:
                    logger.error("Failed to index %s: %s", rel_path, e)

        self.resolve_imports()

    def index_file(self, path: Path, rel_path: str) -> None:
        content = path.read_text(encoding="utf-8", errors="ignore")
        size = len(content)
        ext = path.suffix.lower()

        info = {
            "name": path.name,
            "path": rel_path,
            "size": size,
            "classes": [],
            "functions": [],
            "routes": [],
            "imports": [],
            "imports_raw": [],
            "style": "unknown"
        }

        # Naming convention detection
        if ext in {".py", ".js", ".ts", ".jsx", ".tsx"}:
            if "_" in content and not any(c.isupper() for c in content if c.isalpha()):
                info["style"] = "snake_case"
            elif any(c.isupper() for c in content if c.isalpha()) and "_" not in content:
                info["style"] = "camelCase"

        # Language specific parsing
        if ext == ".py":
            self.parse_python(content, info)
        elif ext in {".js", ".ts", ".jsx", ".tsx"}:
            self.parse_js_ts(content, info)
        elif ext in {".html", ".css", ".json", ".yaml", ".yml", ".md"}:
            pass # Keep basic info

        # Framework detection
        if "fastapi" in content.lower() or "uvicorn" in content.lower():
            self.frameworks.add("FastAPI")
        if "react" in content.lower():
            self.frameworks.add("React")
        if "express" in content.lower():
            self.frameworks.add("Express")
        if "sqlite" in content.lower():
            self.frameworks.add("SQLite")

        # Dependency files scanning
        if path.name == "requirements.txt":
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    self.dependencies.append(line)
        elif path.name == "package.json":
            try:
                import json
                data = json.loads(content)
                deps = data.get("dependencies", {})
                dev_deps = data.get("devDependencies", {})
                for k, v in {**deps, **dev_deps}.items():
                    self.dependencies.append(f"{k}@{v}")
                self.frameworks.add("Node.js")
            except Exception:
                pass

        self.files[rel_path] = info

    def parse_python(self, content: str, info: dict) -> None:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            # Regex fallback
            info["functions"] = re.findall(r"def\s+(\w+)\s*\(", content)
            info["classes"] = re.findall(r"class\s+(\w+)\s*:", content)
            return

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                info["classes"].append(node.name)
            elif isinstance(node, ast.FunctionDef):
                info["functions"].append(node.name)
                # Check for FastAPI / web routes
                for dec in node.decorator_list:
                    dec_str = ast.unparse(dec) if hasattr(ast, "unparse") else ""
                    if any(route_verb in dec_str for route_verb in ["get(", "post(", "put(", "delete(", "patch("]):
                        info["routes"].append({
                            "decorator": dec_str,
                            "function": node.name,
                            "line": node.lineno
                        })
            elif isinstance(node, ast.Import):
                for name in node.names:
                    info["imports_raw"].append(name.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                info["imports_raw"].append(node.module)

    def parse_js_ts(self, content: str, info: dict) -> None:
        # Regex parsing for JS/TS
        info["functions"] = re.findall(r"\bfunction\s+(\w+)\b", content)
        info["functions"].extend(re.findall(r"\bconst\s+(\w+)\s*=\s*\([^)]*\)\s*=>", content))
        info["classes"] = re.findall(r"\bclass\s+(\w+)\b", content)
        
        # Imports parsing
        for match in re.finditer(r"""import\s+.*\s+from\s+['"]([^'"]+)['"]""", content):
            info["imports_raw"].append(match.group(1))
        for match in re.finditer(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""", content):
            info["imports_raw"].append(match.group(1))

    def resolve_imports(self) -> None:
        """Resolve raw imports to actual relative workspace files."""
        for rel_path, info in self.files.items():
            resolved = []
            for imp in info.get("imports_raw", []):
                # Check relative path resolution
                if imp.startswith("."):
                    # Resolve relative to file directory
                    parent = Path(rel_path).parent
                    candidate = (parent / imp).as_posix()
                    # Try matching direct name or with extension
                    for ext in [".py", ".js", ".ts", ".jsx", ".tsx", ""]:
                        test_path = candidate + ext
                        if test_path in self.files:
                            resolved.append(test_path)
                            break
                else:
                    # Check absolute reference to workspace files
                    for p in self.files:
                        if p.startswith(imp) or Path(p).stem == imp:
                            resolved.append(p)
            info["imports"] = list(set(resolved))
            self.import_graph[rel_path] = info["imports"]

    def to_dict(self) -> dict:
        return {
            "frameworks": list(self.frameworks),
            "dependencies": self.dependencies,
            "files": {k: {
                "name": v["name"],
                "size": v["size"],
                "classes": v["classes"],
                "functions": v["functions"],
                "routes": v["routes"],
                "imports": v["imports"],
                "style": v["style"]
            } for k, v in self.files.items()},
            "import_graph": self.import_graph
        }

def get_project_index(project_dir: Path) -> dict:
    idx = ProjectIndex(project_dir)
    idx.scan()
    return idx.to_dict()
