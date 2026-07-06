# app/tests/test_repository_analyzer.py
import unittest
import ast
from app.services.repository_analyzer import PythonSymbolExtractor, parse_javascript_symbols, parse_sql_schemas

class TestRepositoryAnalyzer(unittest.TestCase):
    def test_python_symbol_extractor(self):
        code = """
class Calculator:
    def add(self, a, b):
        \"\"\"Add two numbers.\"\"\"
        return a + b

def global_func():
    pass
"""
        tree = ast.parse(code)
        extractor = PythonSymbolExtractor("dummy_path.py")
        extractor.visit(tree)
        
        symbols = extractor.symbols
        types = [s["type"] for s in symbols]
        self.assertIn("class", types)
        self.assertIn("method", types)
        self.assertIn("function", types)
        
        calc_class = next(s for s in symbols if s["type"] == "class")
        self.assertEqual(calc_class["name"], "Calculator")
        
        add_method = next(s for s in symbols if s["type"] == "method")
        self.assertEqual(add_method["name"], "add")
        self.assertEqual(add_method["docstring"], "Add two numbers.")

    def test_javascript_symbols(self):
        js_code = """
class User {
  constructor() {}
}
const fetchUsers = async () => {};
import { config } from 'dotenv';
"""
        symbols = parse_javascript_symbols(js_code, "dummy.js")
        types = [s["type"] for s in symbols]
        self.assertIn("class", types)
        self.assertIn("function", types)
        self.assertIn("import", types)

    def test_sql_schemas(self):
        sql = "CREATE TABLE users (id INT, name TEXT);"
        symbols = parse_sql_schemas(sql, "schema.sql")
        self.assertEqual(len(symbols), 1)
        self.assertEqual(symbols[0]["name"], "users")
        self.assertEqual(symbols[0]["type"], "schema")
