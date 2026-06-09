# indexing/relationship_indexer.py
#
# LAYER 2 — Symbol Relationship Indexer
#
# Extracts directed edges between symbols and files:
#
#   EXTENDS     — ClassA extends ClassB     (Java/TS AST)
#   IMPLEMENTS  — ClassA implements IFaceB  (Java AST)
#   USES        — FileA imports FileB       (all languages, import statements)
#   TESTS       — TestClass tests ProdClass (naming convention + @Test annotation)
#
# CALLS edges require dynamic/runtime info and are not extracted here.
# They can be added in a future layer using call-site AST analysis.
#
# Storage: symbol_relationships + tests tables
#

import time
from typing import Optional

from db.connection import get_conn
from parsers.registry import registry


class RelationshipIndexer:

    def __init__(self):
        self.extends_count    = 0
        self.implements_count = 0
        self.uses_count       = 0
        self.tests_count      = 0
        self.errors           = 0

    # =========================================================
    # MAIN
    # =========================================================

    def index_repository(self, repo_id: int) -> None:
        files   = self._get_files(repo_id)
        symbols = self._get_symbols_map(repo_id)   # qualified_name -> id
        names   = self._get_symbols_by_name(repo_id)  # name -> [symbol_id, ...]

        print(f"\n[Relationships] Indexing {len(files)} files, {len(symbols)} symbols")
        start = time.time()

        # Clear existing relationships for this repo
        self._clear_relationships(repo_id)

        for f in files:
            lang = f["language"]
            if not registry.supports(lang):
                continue

            parsed = registry.parse_file(f["path"], lang)
            if not parsed or parsed.error:
                self.errors += 1
                continue

            rows = []

            # ── EXTENDS / IMPLEMENTS (Java + TS) ─────────────
            rows += self._extract_hierarchy(f, parsed, names, repo_id)

            # ── USES (all: import-based) ──────────────────────
            rows += self._extract_uses(f, parsed, files, repo_id)

            if rows:
                self._insert_relationships(rows)

            # ── TESTS (naming convention) ─────────────────────
            test_rows = self._extract_tests(f, parsed, names, repo_id)
            if test_rows:
                self._insert_tests(test_rows)

        elapsed = time.time() - start
        print(
            f"[Relationships] Done in {elapsed:.2f}s — "
            f"EXTENDS={self.extends_count} IMPLEMENTS={self.implements_count} "
            f"USES={self.uses_count} TESTS={self.tests_count} errors={self.errors}"
        )

    # =========================================================
    # HIERARCHY: EXTENDS / IMPLEMENTS
    # =========================================================

    def _extract_hierarchy(
        self,
        file_row: dict,
        parsed,
        names_map: dict,
        repo_id: int,
    ) -> list:
        """
        Use tree-sitter to find extends/implements declarations.
        Faster and more accurate than regex.
        """
        rows = []
        lang = file_row["language"]

        if lang == "java":
            rows += self._java_hierarchy(file_row, parsed, names_map, repo_id)
        elif lang in ("typescript", "tsx", "javascript"):
            rows += self._ts_hierarchy(file_row, parsed, names_map, repo_id)

        return rows

    def _java_hierarchy(self, file_row, parsed, names_map, repo_id):
        """
        Re-parse the file with raw tree-sitter to find superclass_type and
        interface names from class_declaration nodes.
        We use the already-parsed class list + re-open the tree for hierarchy.
        """
        rows = []
        try:
            import tree_sitter_java as ts_java
            from tree_sitter import Language, Parser
            from parsers.base import node_text

            lang     = Language(ts_java.language())
            parser   = Parser(lang)
            src      = open(file_row["path"], encoding="utf-8", errors="replace").read()
            src_b    = src.encode("utf-8")
            tree     = parser.parse(src_b)

            self._walk_java_hierarchy(
                tree.root_node, src_b, file_row, names_map, repo_id, rows
            )
        except Exception as e:
            self.errors += 1
        return rows

    def _walk_java_hierarchy(self, node, src, file_row, names_map, repo_id, rows):
        from parsers.base import node_text

        if node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            class_name = node_text(name_node, src)
            from_id    = names_map.get(class_name)

            for child in node.children:
                # extends
                if child.type == "superclass":
                    for gc in child.children:
                        if gc.type == "type_identifier":
                            target = node_text(gc, src)
                            to_id  = names_map.get(target)
                            rows.append(self._rel_row(
                                repo_id, from_id, file_row["id"], class_name,
                                to_id, None, target, "EXTENDS"
                            ))
                            self.extends_count += 1

                # implements
                if child.type == "super_interfaces":
                    for gc in child.children:
                        if gc.type in ("type_list", "interface_type_list"):
                            for ggc in gc.children:
                                if ggc.type == "type_identifier":
                                    target = node_text(ggc, src)
                                    to_id  = names_map.get(target)
                                    rows.append(self._rel_row(
                                        repo_id, from_id, file_row["id"], class_name,
                                        to_id, None, target, "IMPLEMENTS"
                                    ))
                                    self.implements_count += 1

        for child in node.children:
            self._walk_java_hierarchy(child, src, file_row, names_map, repo_id, rows)

    def _ts_hierarchy(self, file_row, parsed, names_map, repo_id):
        """
        For TypeScript: re-parse to find extends/implements on class_declaration nodes.
        """
        rows = []
        try:
            import tree_sitter_typescript as ts_ts
            from tree_sitter import Language, Parser
            from parsers.base import node_text

            tsx  = file_row["language"] == "tsx"
            lang = Language(ts_ts.language_tsx() if tsx else ts_ts.language_typescript())
            parser = Parser(lang)
            src    = open(file_row["path"], encoding="utf-8", errors="replace").read()
            src_b  = src.encode("utf-8")
            tree   = parser.parse(src_b)

            self._walk_ts_hierarchy(tree.root_node, src_b, file_row, names_map, repo_id, rows)
        except Exception as e:
            self.errors += 1
        return rows

    def _walk_ts_hierarchy(self, node, src, file_row, names_map, repo_id, rows):
        from parsers.base import node_text

        if node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            class_name = node_text(name_node, src)
            from_id    = names_map.get(class_name)

            for child in node.children:
                if child.type == "class_heritage":
                    for gc in child.children:
                        if gc.type == "extends_clause":
                            for ggc in gc.children:
                                if ggc.type == "identifier":
                                    target = node_text(ggc, src)
                                    rows.append(self._rel_row(
                                        repo_id, from_id, file_row["id"], class_name,
                                        names_map.get(target), None, target, "EXTENDS"
                                    ))
                                    self.extends_count += 1

                        if gc.type == "implements_clause":
                            for ggc in gc.children:
                                if ggc.type == "type_identifier":
                                    target = node_text(ggc, src)
                                    rows.append(self._rel_row(
                                        repo_id, from_id, file_row["id"], class_name,
                                        names_map.get(target), None, target, "IMPLEMENTS"
                                    ))
                                    self.implements_count += 1

        for child in node.children:
            self._walk_ts_hierarchy(child, src, file_row, names_map, repo_id, rows)

    # =========================================================
    # USES: import-based file dependencies
    # =========================================================

    def _extract_uses(self, file_row, parsed, all_files, repo_id):
        """
        Import statements → USES edges between files.
        Maps import paths to file IDs using the files list.
        """
        rows = []
        file_map = {f["relative_path"]: f["id"] for f in all_files}
        from_file_id = file_row["id"]
        from_name    = file_row["relative_path"]

        for imp in parsed.imports:
            target_name = imp.name.strip()
            to_file_id  = self._resolve_import(target_name, file_map, file_row)

            rows.append(self._rel_row(
                repo_id,
                None, from_file_id, from_name,
                None, to_file_id,   target_name,
                "USES"
            ))
            self.uses_count += 1

        return rows

    def _resolve_import(self, import_str: str, file_map: dict, file_row: dict) -> Optional[int]:
        """Try to resolve an import string to a file_id."""
        # Java: com.acme.hrms.employee.EmployeeService → .../EmployeeService.java
        # TS:   ../services/employeeService → .../employeeService.ts
        clean = import_str.replace("import ", "").split(" ")[0].rstrip(";").strip()
        # Remove leading { } for named imports
        clean = clean.strip("{}").strip()

        # Try by last segment as filename
        last = clean.split(".")[-1].split("/")[-1]
        for rpath, fid in file_map.items():
            base = rpath.split("/")[-1].rsplit(".", 1)[0]
            if base.lower() == last.lower():
                return fid
        return None

    # =========================================================
    # TESTS: naming convention detection
    # =========================================================

    def _extract_tests(self, file_row, parsed, names_map, repo_id):
        """
        Detect test classes/methods using naming conventions:
          - Class ends with 'Test' or 'Tests' or starts with 'Test'
          - File is in test/ directory
        """
        rows = []
        path  = file_row["relative_path"].lower()
        is_test = (
            "/test/" in path or
            "/tests/" in path or
            "test/" in path or
            any(
                c.name.lower().endswith("test") or
                c.name.lower().endswith("tests") or
                c.name.lower().startswith("test")
                for c in parsed.classes
            )
        )
        if not is_test:
            return rows

        for cls in parsed.classes:
            if not (
                cls.name.lower().endswith("test") or
                cls.name.lower().endswith("tests") or
                cls.name.lower().startswith("test")
            ):
                continue

            # Convention: EmployeeControllerTest → EmployeeController
            stripped = cls.name
            for suffix in ("Test", "Tests", "IT", "Spec"):
                if stripped.endswith(suffix):
                    stripped = stripped[:-len(suffix)]
                    break
            if stripped.startswith("Test"):
                stripped = stripped[4:]

            test_sym_id   = names_map.get(cls.name)
            target_sym_id = names_map.get(stripped)

            cls_sym_id = names_map.get(cls.name)
            test_row   = (
                repo_id,
                file_row["id"],
                cls_sym_id,
                cls.name,
                None,
                target_sym_id,
                stripped if stripped else None,
                "naming_convention",
            )
            rows.append(test_row)
            self.tests_count += 1

        return rows

    # =========================================================
    # DB OPERATIONS
    # =========================================================

    def _clear_relationships(self, repo_id: int) -> None:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM symbol_relationships WHERE repository_id = %s",
                    (repo_id,)
                )
                cur.execute(
                    "DELETE FROM tests WHERE repository_id = %s",
                    (repo_id,)
                )

    def _insert_relationships(self, rows: list) -> None:
        sql = """
            INSERT INTO symbol_relationships
                (repository_id, from_symbol_id, from_file_id, from_name,
                 to_symbol_id, to_file_id, to_name, rel_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)

    def _insert_tests(self, rows: list) -> None:
        sql = """
            INSERT INTO tests
                (repository_id, test_file_id, test_symbol_id, test_name,
                 target_file_id, target_symbol_id, target_name, detection_method)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)

    def _get_files(self, repo_id: int) -> list:
        sql = "SELECT id, path, relative_path, language FROM files WHERE repository_id = %s ORDER BY id"
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (repo_id,))
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, r)) for r in cur.fetchall()]

    def _get_symbols_map(self, repo_id: int) -> dict:
        """qualified_name -> symbol_id"""
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT qualified_name, id FROM symbols WHERE repository_id = %s AND qualified_name IS NOT NULL",
                    (repo_id,)
                )
                return {row[0]: row[1] for row in cur.fetchall()}

    def _get_symbols_by_name(self, repo_id: int) -> dict:
        """name -> symbol_id (first match)"""
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT name, id FROM symbols WHERE repository_id = %s",
                    (repo_id,)
                )
                result = {}
                for name, sid in cur.fetchall():
                    if name not in result:
                        result[name] = sid
                return result

    # =========================================================
    # HELPERS
    # =========================================================

    @staticmethod
    def _rel_row(
        repo_id,
        from_symbol_id, from_file_id, from_name,
        to_symbol_id, to_file_id, to_name,
        rel_type,
    ):
        return (
            repo_id,
            from_symbol_id, from_file_id, from_name,
            to_symbol_id,   to_file_id,   to_name,
            rel_type,
        )
