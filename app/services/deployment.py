from __future__ import annotations
import ast
import re
from pathlib import Path
from app.services.language import detect_language

PYTHON_STDLIB = {
    "abc", "aifc", "argparse", "array", "ast", "asyncio", "base64", "bisect",
    "calendar", "collections", "contextlib", "copy", "csv", "dataclasses",
    "datetime", "decimal", "enum", "functools", "glob", "hashlib", "heapq",
    "html", "http", "importlib", "inspect", "io", "itertools", "json",
    "logging", "math", "mimetypes", "operator", "os", "pathlib", "pdb",
    "pickle", "platform", "pprint", "queue", "random", "re", "secrets",
    "shutil", "signal", "socket", "sqlite3", "statistics", "string",
    "struct", "subprocess", "sys", "tempfile", "textwrap", "threading",
    "time", "traceback", "types", "typing", "unittest", "urllib", "uuid",
    "warnings", "weakref", "xml", "zipfile",
}

PIP_NAME_MAP = {
    "PIL": "pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "yaml": "pyyaml",
    "dotenv": "python-dotenv",
    "bs4": "beautifulsoup4",
}

def extract_python_imports(code: str) -> list[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module.split(".")[0])
    return sorted(set(modules))

def extract_npm_packages(code: str) -> list[str]:
    packages: set[str] = set()
    for match in re.finditer(r"""require\s*\(\s*['"]([^./][^'"]*)['"]\)""", code):
        packages.add(match.group(1).split("/")[0])
    for match in re.finditer(r"""from\s+['"]([^./][^'"]*)['"]""", code):
        packages.add(match.group(1).split("/")[0])
    return sorted(packages)

def get_deployment_info(code: str, filename: str) -> dict:
    ext = Path(filename).suffix.lower()
    
    # Extension to language map
    ext_map = {
        ".py": "python",
        ".js": "javascript",
        ".mjs": "javascript",
        ".ts": "typescript",
        ".jsx": "jsx",
        ".tsx": "react",
        ".html": "html",
        ".htm": "html",
        ".css": "css",
        ".json": "json",
        ".java": "java",
        ".kt": "kotlin",
        ".kts": "kotlin",
        ".cs": "csharp",
        ".go": "go",
        ".rs": "rust",
        ".c": "c",
        ".h": "c",
        ".cpp": "cpp",
        ".hpp": "cpp",
        ".cc": "cpp",
        ".rb": "ruby",
        ".php": "php",
        ".sql": "sql",
        ".sh": "bash",
        ".ps1": "powershell",
        ".r": "r",
        ".lua": "lua",
        ".scala": "scala",
        ".swift": "swift",
    }
    
    language = ext_map.get(ext) or detect_language(code, "auto")
    
    requirements: list[str] = []
    run_command = ""
    system_requirements = ""
    
    if language == "python":
        imports = extract_python_imports(code)
        reqs = []
        for imp in imports:
            if imp in PYTHON_STDLIB:
                continue
            pip_name = PIP_NAME_MAP.get(imp, imp)
            reqs.append(pip_name)
        if reqs:
            requirements = [f"pip install {' '.join(reqs)}"]
        else:
            requirements = ["No external library dependencies (Standard Library only)."]
        run_command = f"python {filename}"
        system_requirements = "Python 3.11+"
        
    elif language in {"javascript", "typescript", "jsx", "react"}:
        pkgs = extract_npm_packages(code)
        if pkgs:
            requirements = [f"npm install {' '.join(pkgs)}"]
        else:
            requirements = ["No external npm packages required."]
        
        if language == "typescript":
            run_command = f"npx tsx {filename}"
            system_requirements = "Node.js 18+ (with npx)"
        elif language in {"jsx", "react"}:
            requirements.append("Requires React bundler (Vite, Next.js, or equivalent) to compile in production.")
            run_command = "npm run dev / npm run build"
            system_requirements = "Node.js 18+ & Bundler"
        else:
            run_command = f"node {filename}"
            system_requirements = "Node.js 18+"
            
    elif language == "html":
        requirements = ["No dependencies. Open directly in a browser."]
        run_command = f"Double-click {filename} to open in any web browser"
        system_requirements = "Any modern Web Browser (Chrome, Firefox, Safari, Edge)"
        
    elif language == "css":
        requirements = ["Reference in your HTML file via <link rel=\"stylesheet\" href=\"...\">"]
        run_command = "Include stylesheet in HTML page and open HTML in a web browser"
        system_requirements = "Any modern Web Browser"
        
    elif language == "json":
        requirements = ["Valid configuration or data file."]
        run_command = "Read/Parse using your chosen language parser (e.g. json.load() in Python)"
        system_requirements = "Any environment with a JSON parser"
        
    elif language == "java":
        requirements = ["Requires Java Compiler (javac) and Virtual Machine (java)."]
        class_match = re.search(r"\b(?:public\s+)?class\s+(\w+)", code)
        class_name = class_match.group(1) if class_match else "Main"
        run_command = f"javac {filename} && java {class_name}"
        system_requirements = "Java JDK 17+"
        
    elif language == "kotlin":
        requirements = ["Kotlin Compiler (kotlinc) & JVM environment."]
        run_command = f"kotlinc {filename} -include-runtime -d app.jar && java -jar app.jar"
        system_requirements = "Kotlin Compiler + Java JRE"
        
    elif language == "csharp":
        requirements = ["Requires .NET SDK."]
        run_command = "dotnet run"
        system_requirements = ".NET SDK 8.0+"
        
    elif language == "go":
        requirements = ["Go compiler."]
        run_command = f"go run {filename}"
        system_requirements = "Go compiler"
        
    elif language == "rust":
        requirements = ["Rust toolchain."]
        run_command = f"rustc {filename} && ./{Path(filename).stem}"
        system_requirements = "Rust toolchain (cargo/rustc)"
        
    elif language == "c":
        requirements = ["C compiler (GCC or Clang)."]
        run_command = f"gcc {filename} -o app && ./app"
        system_requirements = "GCC or Clang"
        
    elif language == "cpp":
        requirements = ["C++ compiler (G++ or Clang++)."]
        run_command = f"g++ {filename} -o app && ./app"
        system_requirements = "G++ or Clang++"
        
    elif language == "ruby":
        requirements = ["Ruby interpreter."]
        run_command = f"ruby {filename}"
        system_requirements = "Ruby interpreter"
        
    elif language == "php":
        requirements = ["PHP runtime."]
        run_command = f"php {filename}"
        system_requirements = "PHP CLI"
        
    elif language == "sql":
        requirements = ["SQL database system (e.g. SQLite, PostgreSQL, MySQL)."]
        run_command = f"sqlite3 database.db < {filename}  # (For SQLite)"
        system_requirements = "Any database engine"
        
    elif language in {"bash", "shell"}:
        requirements = ["Unix shell environment."]
        run_command = f"bash {filename}"
        system_requirements = "Bash or compatible shell"
        
    elif language == "powershell":
        requirements = ["PowerShell environment."]
        run_command = f"powershell -File {filename}"
        system_requirements = "PowerShell 5.1+ or PowerShell Core"
        
    elif language == "r":
        requirements = ["R environment."]
        run_command = f"Rscript {filename}"
        system_requirements = "R environment"
        
    elif language == "lua":
        requirements = ["Lua interpreter."]
        run_command = f"lua {filename}"
        system_requirements = "Lua interpreter"
        
    elif language == "scala":
        requirements = ["Scala runtime & JVM."]
        run_command = f"scala {filename}"
        system_requirements = "Scala CLI & Java JRE"
        
    elif language == "swift":
        requirements = ["Swift toolchain."]
        run_command = f"swift {filename}"
        system_requirements = "Swift Compiler"
        
    else:
        requirements = ["Verify library imports or requirements manually."]
        run_command = "# Command dependent on target environment"
        system_requirements = "Standard compiler/interpreter for language"
        
    return {
        "language": language,
        "requirements": requirements,
        "run_command": run_command,
        "system_requirements": system_requirements
    }
