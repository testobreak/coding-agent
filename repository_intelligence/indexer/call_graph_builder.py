# repository_intelligence/indexer/call_graph_builder.py
"""
Call Graph Builder for Java source files.

Extracts method-call edges from Java AST using tree-sitter and resolves the
receiver type via TypeResolver.  Spring Framework synthetic stubs are
generated so that calls into JPA/Spring remain trackable even without
parsing library source.

Edge format:  ExtractedRelationship(
    source_qualified_name = "com.example.EmployeeServiceImpl.createEmployee",
    target_name           = "spring.JpaRepository#save(T)",
    relationship_type     = "CALLS",
    confidence            = 0.9,
)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from tree_sitter import Language, Parser
import tree_sitter_java as ts_java

from repository_intelligence.indexer.symbol_extractor import ExtractedRelationship

# ---------------------------------------------------------------------------
# Spring / JPA Framework stubs
# ---------------------------------------------------------------------------

SPRING_STUBS: Dict[str, List[str]] = {
    "JpaRepository": ["save", "saveAll", "findById", "findAll", "findAllById",
                      "existsById", "count", "delete", "deleteById", "deleteAll",
                      "flush", "saveAndFlush"],
    "CrudRepository": ["save", "saveAll", "findById", "existsById", "findAll",
                       "count", "delete", "deleteById"],
    "PagingAndSortingRepository": ["findAll"],
    "MongoRepository": ["save", "findAll", "findById", "delete", "deleteById",
                        "count", "existsById", "insert"],
    "ElasticsearchRepository": ["save", "findById", "delete", "search"],
    "JdbcTemplate": ["query", "queryForObject", "queryForList", "update",
                     "batchUpdate", "execute"],
    "RestTemplate": ["getForObject", "getForEntity", "postForObject",
                     "postForEntity", "exchange", "delete"],
    "ApplicationEventPublisher": ["publishEvent"],
}


def _spring_qualified(class_name: str, method_name: str) -> str:
    return f"spring.{class_name}#{method_name}"


# Pre-build a lookup: method_name -> list of spring qualified names
_STUB_BY_METHOD: Dict[str, List[str]] = {}
for _cls, _methods in SPRING_STUBS.items():
    for _m in _methods:
        _STUB_BY_METHOD.setdefault(_m, []).append(_spring_qualified(_cls, _m))


# ---------------------------------------------------------------------------
# Data class for an extracted call
# ---------------------------------------------------------------------------

@dataclass
class ExtractedCall:
    receiver: Optional[str]          # variable name, e.g. "employeeRepository"
    method_name: str                  # e.g. "save"
    enclosing_method: Optional[str]   # qualified name of the caller method
    args: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# CallGraphBuilder
# ---------------------------------------------------------------------------

class CallGraphBuilder:
    """Extract method-call relationships from a Java source file.

    Usage::

        builder = CallGraphBuilder()
        relationships = builder.extract(
            file_path="...",
            source="...",
            symbol_table={"employeeRepository": "EmployeeRepository"},
            file_namespace="com.example.service",
        )
    """

    def __init__(self) -> None:
        self._parser = Parser(Language(ts_java.language()))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(
        self,
        file_path: str,
        source: Optional[str] = None,
        symbol_table: Optional[Dict[str, str]] = None,
        file_namespace: str = "",
    ) -> List[ExtractedRelationship]:
        """Return a list of CALLS ExtractedRelationship objects for the file."""
        if source is None:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()

        src_bytes = source.encode("utf-8")
        tree = self._parser.parse(src_bytes)
        symbol_table = symbol_table or {}

        calls = self._extract_calls(tree.root_node, src_bytes, symbol_table)
        return self._calls_to_relationships(calls, symbol_table, file_namespace)

    # ------------------------------------------------------------------
    # Step 4.1 — Extract method invocations from AST
    # ------------------------------------------------------------------

    def _extract_calls(
        self,
        root,
        src: bytes,
        symbol_table: Dict[str, str],
    ) -> List[ExtractedCall]:
        """Walk the tree and collect every method_invocation node."""
        calls: List[ExtractedCall] = []
        self._walk(root, src, calls, enclosing_method=None)
        return calls

    def _walk(self, node, src: bytes, calls: List[ExtractedCall],
              enclosing_method: Optional[str]) -> None:
        t = node.type

        # Track enclosing method
        if t in ("method_declaration", "constructor_declaration"):
            name_node = node.child_by_field_name("name")
            if name_node:
                enclosing_method = self._text(name_node, src)

        # Capture method invocation
        if t == "method_invocation":
            call = self._parse_invocation(node, src, enclosing_method)
            if call:
                calls.append(call)

        for child in node.children:
            self._walk(child, src, calls, enclosing_method)

    def _parse_invocation(self, node, src: bytes,
                          enclosing_method: Optional[str]) -> Optional[ExtractedCall]:
        """Parse a single method_invocation node."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        method_name = self._text(name_node, src)

        # Object part: foo.bar() → receiver = "foo"
        obj_node = node.child_by_field_name("object")
        receiver: Optional[str] = None
        if obj_node:
            raw = self._text(obj_node, src)
            # Strip "this." prefix if present
            receiver = raw.lstrip("this.") if raw.startswith("this.") else raw
            # If chained (e.g. a.b.save), take the last segment as the receiver variable
            if "." in receiver:
                receiver = receiver.split(".")[-2]  # a.b → b

        # Arguments
        args_node = node.child_by_field_name("arguments")
        args: List[str] = []
        if args_node:
            for child in args_node.children:
                if child.type not in (",", "(", ")"):
                    args.append(self._text(child, src))

        return ExtractedCall(
            receiver=receiver,
            method_name=method_name,
            enclosing_method=enclosing_method,
            args=args,
        )

    # ------------------------------------------------------------------
    # Step 4.2 + 4.3 + 4.4 — Resolve & produce relationships
    # ------------------------------------------------------------------

    def _calls_to_relationships(
        self,
        calls: List[ExtractedCall],
        symbol_table: Dict[str, str],
        file_namespace: str,
    ) -> List[ExtractedRelationship]:
        relationships: List[ExtractedRelationship] = []

        for call in calls:
            # Build qualified source name
            source_qn = (
                f"{file_namespace}.{call.enclosing_method}"
                if file_namespace and call.enclosing_method
                else call.enclosing_method
            )

            # Step 4.2 — resolve receiver type
            receiver_type: Optional[str] = None
            if call.receiver:
                receiver_type = symbol_table.get(call.receiver)
                # Also try lowercase-first (e.g. "EmployeeRepository" field stored as type)
                if not receiver_type:
                    receiver_type = symbol_table.get(
                        call.receiver[0].lower() + call.receiver[1:]
                    )

            # Step 4.3 — build target qualified name
            if receiver_type:
                # Strip generic part: EmployeeRepository<Employee, Long> → EmployeeRepository
                base_type = re.sub(r"<.*>", "", receiver_type).strip()
                target_qn = f"{base_type}.{call.method_name}"
                confidence = 0.9
            else:
                # No receiver → unqualified call
                target_qn = call.method_name
                confidence = 0.5

            # Step 4.4 — check if target is a Spring stub method
            stub_targets = _STUB_BY_METHOD.get(call.method_name, [])
            if stub_targets and receiver_type:
                base_type = re.sub(r"<.*>", "", receiver_type or "").strip()
                # If receiver is a known Spring subtype (e.g. EmployeeRepository extends JpaRepository)
                # emit edge to each matching Spring stub
                for stub in stub_targets:
                    relationships.append(ExtractedRelationship(
                        source_qualified_name=source_qn,
                        target_name=stub,
                        relationship_type="CALLS",
                        confidence=0.75,
                        metadata={"stub": True, "method": call.method_name},
                    ))

            # Primary CALLS edge (concrete target)
            relationships.append(ExtractedRelationship(
                source_qualified_name=source_qn,
                target_name=target_qn,
                relationship_type="CALLS",
                confidence=confidence,
                metadata={"receiver": call.receiver, "args": call.args},
            ))

        return relationships

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _text(self, node, src: bytes) -> str:
        return src[node.start_byte: node.end_byte].decode("utf-8", errors="replace").strip()
