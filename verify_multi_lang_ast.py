# verify_multi_lang_ast.py
import sys
import os

from repository_intelligence.parsers import get_parser

def test_python_ast():
    print("[Test] Verifying Python AST locator...")
    code = "class Calculator:\n    def add(self, a, b):\n        return a + b\n"
    temp_file = "temp_calc.py"
    with open(temp_file, "w") as f:
        f.write(code)

    try:
        parser = get_parser(temp_file)
        symbols = parser.extract_symbols(temp_file)
        names = [s["name"] for s in symbols]
        assert "Calculator" in names
        assert "add" in names
        
        loc = parser.locate_symbol(temp_file, "add")
        assert loc is not None
        assert loc[0] == 2
        print("  [OK] Python AST locator verified.")
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)

def test_java_ast():
    print("[Test] Verifying Java AST locator & annotation expansion...")
    code = "package com.example;\n\n@Transactional\npublic class EmployeeService {\n    @Autowired\n    private EmployeeRepo repo;\n\n    @Override\n    public void save() {\n        repo.save();\n    }\n}\n"
    temp_file = "temp_service.java"
    with open(temp_file, "w") as f:
        f.write(code)

    try:
        parser = get_parser(temp_file)
        symbols = parser.extract_symbols(temp_file)
        names = [s["name"] for s in symbols]
        assert "EmployeeService" in names
        assert "save" in names

        start, end = parser.expand_edit_region(temp_file, 4, 4)
        assert start == 3
        
        start_m, end_m = parser.expand_edit_region(temp_file, 9, 11)
        assert start_m == 8
        print("  [OK] Java AST locator and annotations verified.")
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)

class ExtractedSymbol:
    def __init__(self, name, qualified_name, symbol_type, start_line, end_line, signature="", parent_qualified_name=None, metadata=None, source_hash=""):
        self.name = name
        self.qualified_name = qualified_name
        self.symbol_type = symbol_type
        self.start_line = start_line
        self.end_line = end_line
        self.signature = signature
        self.parent_qualified_name = parent_qualified_name
        self.metadata = metadata or {}
        self.source_hash = source_hash or "mock_hash"

def test_symbol_span_db():
    print("[Test] Verifying SymbolSpan DB insertion & Java signature resolution...")
    from repository_intelligence.db.connection import SessionLocal, Base, engine
    from repository_intelligence.models.repository import Repository
    from repository_intelligence.models.file import File
    from repository_intelligence.models.symbol import SymbolSpan
    from repository_intelligence.services.repository_service import RepositoryService

    Base.metadata.create_all(bind=engine)
    session = SessionLocal()

    # Create mock Repository
    repo = Repository(name="CodingAgent-Test", root_path=os.getcwd())
    session.add(repo)
    session.flush()

    # Create mock File
    file_row = File(
        repository_id=repo.id,
        path="temp_service.java",
        language="java",
        file_hash="mock_hash",
        size_bytes=100
    )
    session.add(file_row)
    session.flush()

    # Write file content to disk
    code = "package com.example;\npublic class EmployeeService {\n    public void save(Employee e) {}\n    public void save(List<Employee> employees) {}\n}\n"
    full_path = os.path.join(os.getcwd(), file_row.path)
    with open(full_path, "w") as f:
        f.write(code)

    # Mock Extracted Symbols
    e1 = ExtractedSymbol(
        name="EmployeeService",
        qualified_name="com.example.EmployeeService",
        symbol_type="class",
        start_line=2,
        end_line=5
    )
    e2 = ExtractedSymbol(
        name="save",
        qualified_name="com.example.EmployeeService.save",
        symbol_type="method",
        start_line=3,
        end_line=3,
        signature="public void save(Employee e)"
    )
    e3 = ExtractedSymbol(
        name="save",
        qualified_name="com.example.EmployeeService.save",
        symbol_type="method",
        start_line=4,
        end_line=4,
        signature="public void save(List<Employee> employees)"
    )

    try:
        service = RepositoryService()
        service._persist_symbols(session, repo, file_row, [e1, e2, e3])
        session.commit()

        # Query and assert spans
        spans = session.query(SymbolSpan).filter(SymbolSpan.file_id == file_row.id).all()
        assert len(spans) == 3
        
        # Verify signature mapping
        signatures = [s.qualified_signature for s in spans]
        assert "com.example.EmployeeService.save(Employee)" in signatures
        assert "com.example.EmployeeService.save(List<Employee>)" in signatures
        print("  [OK] SymbolSpan DB insertion and Java overloads verified.")
    finally:
        if os.path.exists(full_path):
            os.remove(full_path)
        session.query(SymbolSpan).filter(SymbolSpan.file_id == file_row.id).delete()
        session.delete(file_row)
        session.delete(repo)
        session.commit()
        session.close()

def test_typescript_ast():
    print("[Test] Verifying TypeScript AST locator & arrow functions...")
    code = "interface EmployeeDTO {\n    id: number;\n    name: string;\n}\n\nconst updateEmployee = async (id: number, data: EmployeeDTO) => {\n    console.log(id);\n};\n"
    temp_file = "temp_service.ts"
    with open(temp_file, "w") as f:
        f.write(code)

    try:
        parser = get_parser(temp_file)
        symbols = parser.extract_symbols(temp_file)
        names = [s["name"] for s in symbols]
        assert "EmployeeDTO" in names
        assert "updateEmployee" in names

        loc = parser.locate_symbol(temp_file, "updateEmployee")
        assert loc is not None
        assert loc[0] == 6
        print("  [OK] TypeScript arrow functions and interfaces verified.")
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)

def main():
    print("============================================================")
    print("  Multi-Language AST Span Locator Verification Suite")
    print("============================================================")
    try:
        test_python_ast()
        test_java_ast()
        test_typescript_ast()
        test_symbol_span_db()
        print("============================================================")
        print("  ALL MULTI-LANGUAGE AST CHECKS PASSED SUCCESSFULLY! [OK]")
        print("============================================================\n")
    except AssertionError as ae:
        print(f"  [FAIL] Assertion error: {ae}")
        sys.exit(1)
    except Exception as e:
        print(f"  [FAIL] Exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
