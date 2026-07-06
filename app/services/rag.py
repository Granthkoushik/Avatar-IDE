# app/services/rag.py
from __future__ import annotations

import os
import sqlite3
import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List

from app.services.config_manager import get_setting
from app.services.repository_analyzer import get_db_connection

logger = logging.getLogger("avatar.rag")

class RetrievalAugmentedGenerator:
    """RAG engine for repository indexing, semantic keyword matching, and document context retrieval."""
    
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir).resolve()
        self.project_id = self.base_dir.name

    def _init_chunk_schema(self, conn: sqlite3.Connection):
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    hash TEXT NOT NULL
                )
            """)

    def _chunk_text(self, text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
        if not text:
            return []
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end])
            start += chunk_size - chunk_overlap
        return chunks

    def run_incremental_indexing(self) -> None:
        """Scan workspace and slice changed files into text chunks in the database."""
        conn = get_db_connection(self.project_id)
        self._init_chunk_schema(conn)
        
        chunk_size = get_setting("rag.chunk_size", 500)
        chunk_overlap = get_setting("rag.chunk_overlap", 50)
        
        ignored_patterns = {
            "node_modules", ".venv", "venv", "dist", "build", ".cache", 
            "coverage", ".git", "__pycache__", ".symbols.db"
        }
        
        for root, dirs, files in os.walk(str(self.base_dir)):
            dirs[:] = [d for d in dirs if d not in ignored_patterns]
            for f in files:
                file_path = Path(root) / f
                if file_path.suffix.lower() not in {".py", ".js", ".ts", ".html", ".css", ".json", ".md", ".sql", ".yaml", ".yml"}:
                    continue
                    
                rel_path = str(file_path.relative_to(self.base_dir)).replace("\\", "/")
                
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    file_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
                except Exception:
                    continue
                    
                # Check if hash matches
                with conn:
                    row = conn.execute("SELECT hash FROM file_hashes WHERE file_path = ?", (rel_path,)).fetchone()
                    if row and row["hash"] == file_hash:
                        # Already indexed
                        continue
                        
                    logger.info("RAG indexing file: %s", rel_path)
                    
                    # Slicing
                    chunks = self._chunk_text(content, chunk_size, chunk_overlap)
                    conn.execute("DELETE FROM chunks WHERE file_path = ?", (rel_path,))
                    for idx, chunk_content in enumerate(chunks):
                        chunk_id = f"{rel_path}:{idx}"
                        conn.execute("""
                            INSERT OR REPLACE INTO chunks (id, file_path, chunk_index, content, hash)
                            VALUES (?, ?, ?, ?, ?)
                        """, (chunk_id, rel_path, idx, chunk_content, file_hash))
                        
                    conn.execute("""
                        INSERT OR REPLACE INTO file_hashes (file_path, hash, last_updated)
                        VALUES (?, ?, ?)
                    """, (rel_path, file_hash, os.path.getmtime(str(file_path))))

    async def retrieve_context(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Retrieve relevant files and code snippets matching query words and symbols."""
        # Index workspace first
        self.run_incremental_indexing()
        
        logger.info("RAG Context retrieval search: %s", query)
        conn = get_db_connection(self.project_id)
        self._init_chunk_schema(conn)
        
        query_words = set(query.lower().split())
        if not query_words:
            return []
            
        results: dict[str, dict[str, Any]] = {}
        
        # 1. Score matching text chunks
        with conn:
            rows = conn.execute("SELECT file_path, content FROM chunks").fetchall()
            for r in rows:
                content_lower = r["content"].lower()
                # Compute simple keyword relevance score
                score = sum(content_lower.count(word) for word in query_words)
                if score > 0:
                    path = r["file_path"]
                    if path not in results:
                        results[path] = {
                            "path": path,
                            "score": score,
                            "snippet": r["content"]
                        }
                    else:
                        results[path]["score"] += score
                        
        # 2. Boost files containing matched symbols from query
        with conn:
            # Check symbols match
            for word in query_words:
                if len(word) < 3:
                    continue
                sym_rows = conn.execute("SELECT file_path, signature FROM symbols WHERE name LIKE ?", (f"%{word}%",)).fetchall()
                for sr in sym_rows:
                    path = sr["file_path"]
                    boost = 15
                    if path in results:
                        results[path]["score"] += boost
                    else:
                        # Fetch top snippet
                        snippet_row = conn.execute("SELECT content FROM chunks WHERE file_path = ? ORDER BY chunk_index LIMIT 1", (path,)).fetchone()
                        snip = snippet_row["content"] if snippet_row else sr["signature"]
                        results[path] = {
                            "path": path,
                            "score": boost,
                            "snippet": snip
                        }
                        
        sorted_results = list(results.values())
        sorted_results.sort(key=lambda x: x["score"], reverse=True)
        return sorted_results[:limit]
