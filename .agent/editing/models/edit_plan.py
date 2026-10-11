# editing/models/edit_plan.py
#
# Symbol-centric edit plan model layer.
#
# Rule #1: No component is allowed to modify a file directly.
# Only: EditOperation → Patch → Transaction → Materialization.
#
# The planner only emits EditPlan subclasses.
# It never sees: AST, files, TreeSitter, or PatchSet.

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from .edit_operation import EditOperation


@dataclass
class EditPlan:
    """Base class for all symbol-centric edit plans.

    An EditPlan is the unit of intent emitted by the Planner.
    It describes *what* needs to change, never *how*.

    The EditExecutor is responsible for translating an EditPlan into
    concrete Patch objects via the appropriate LanguageAdapter.

    Fields
    ------
    operation : EditOperation
        The kind of structural transformation required.
    symbol : str
        Fully-qualified symbol name, e.g. ``EmployeeService.saveEmployee``.
        No file paths — the resolver handles location.
    goal : str
        Natural-language description of the desired outcome.
    file_path : str, optional
        Hint for the symbol resolver when the symbol name is ambiguous across
        multiple files. Should be a repo-relative path.
    extra : dict, optional
        Arbitrary extra fields for operation-specific metadata. Prefer using
        typed subclasses instead.
    """

    operation: EditOperation
    symbol: str
    goal: str
    file_path: Optional[str] = None
    extra: Optional[Dict[str, Any]] = field(default_factory=dict)

    # Alias so legacy code using .instruction still works during migration
    @property
    def instruction(self) -> str:
        return self.goal

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "operation": self.operation.value if isinstance(self.operation, EditOperation) else self.operation,
            "symbol": self.symbol,
            "goal": self.goal,
        }
        if self.file_path:
            data["file_path"] = self.file_path
        if self.extra:
            data.update(self.extra)
        return data

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EditPlan":
        op_val = d.get("operation", "")
        try:
            operation = EditOperation(op_val)
        except ValueError:
            # Unknown operation — store as raw string for forward-compatibility
            operation = op_val  # type: ignore[assignment]
        return cls(
            operation=operation,
            symbol=d.get("symbol", ""),
            goal=d.get("goal") or d.get("instruction", ""),
            file_path=d.get("file_path"),
            extra={k: v for k, v in d.items() if k not in ("operation", "symbol", "goal", "file_path", "instruction")},
        )


# ─────────────────────────────────────────────────────────────────────────────
# Typed subclasses — preferred over raw EditPlan for clarity and static analysis
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ReplaceMethodBody(EditPlan):
    """Replace the body of an existing method while preserving its signature."""

    operation: EditOperation = field(default=EditOperation.REPLACE_METHOD_BODY, init=False)


@dataclass
class AddMethod(EditPlan):
    """Add a new method to an existing class symbol.

    Extra fields
    ------------
    parent_class : str
        Fully-qualified name of the class that will receive the new method.
    """

    operation: EditOperation = field(default=EditOperation.ADD_METHOD, init=False)

    @property
    def parent_class(self) -> Optional[str]:
        return (self.extra or {}).get("parent_class")


@dataclass
class DeleteMethod(EditPlan):
    """Delete a method from its containing class."""

    operation: EditOperation = field(default=EditOperation.DELETE_METHOD, init=False)


@dataclass
class RenameSymbol(EditPlan):
    """Rename a symbol and update all call-sites found by the resolver.

    Extra fields
    ------------
    new_name : str
        The desired new identifier.
    """

    operation: EditOperation = field(default=EditOperation.RENAME_SYMBOL, init=False)

    @property
    def new_name(self) -> Optional[str]:
        return (self.extra or {}).get("new_name")


@dataclass
class MoveSymbol(EditPlan):
    """Move a symbol to a different class or file.

    Extra fields
    ------------
    target_class : str, optional
    target_file  : str, optional
    """

    operation: EditOperation = field(default=EditOperation.MOVE_SYMBOL, init=False)

    @property
    def target_class(self) -> Optional[str]:
        return (self.extra or {}).get("target_class")

    @property
    def target_file(self) -> Optional[str]:
        return (self.extra or {}).get("target_file")


@dataclass
class AddImport(EditPlan):
    """Add an import statement at the top of a file.

    Extra fields
    ------------
    import_statement : str
        The raw import line to insert, e.g. ``import org.slf4j.Logger;``
    """

    operation: EditOperation = field(default=EditOperation.ADD_IMPORT, init=False)

    @property
    def import_statement(self) -> Optional[str]:
        return (self.extra or {}).get("import_statement")


@dataclass
class ModifySignature(EditPlan):
    """Change a method's signature (parameters, return type, visibility)."""

    operation: EditOperation = field(default=EditOperation.MODIFY_SIGNATURE, init=False)


@dataclass
class InsertStatement(EditPlan):
    """Insert one or more statements at a specific location within a method body.

    Extra fields
    ------------
    anchor : str
        A unique string in the method body to use as insertion anchor.
    position : str
        ``"before"`` or ``"after"`` the anchor line.
    """

    operation: EditOperation = field(default=EditOperation.INSERT_STATEMENT, init=False)

    @property
    def anchor(self) -> Optional[str]:
        return (self.extra or {}).get("anchor")

    @property
    def position(self) -> str:
        return (self.extra or {}).get("position", "after")


@dataclass
class DeleteStatement(EditPlan):
    """Delete one or more statements matching a pattern inside a method."""

    operation: EditOperation = field(default=EditOperation.DELETE_STATEMENT, init=False)


@dataclass
class AddAnnotation(EditPlan):
    """Add an annotation/decorator to a class, method, or field.

    Extra fields
    ------------
    annotation : str
        The annotation text, e.g. ``@Transactional`` or ``@Override``.
    """

    operation: EditOperation = field(default=EditOperation.ADD_ANNOTATION, init=False)

    @property
    def annotation(self) -> Optional[str]:
        return (self.extra or {}).get("annotation")


@dataclass
class RemoveAnnotation(EditPlan):
    """Remove an annotation/decorator from a symbol."""

    operation: EditOperation = field(default=EditOperation.REMOVE_ANNOTATION, init=False)


@dataclass
class RefreshDocstring(EditPlan):
    """Regenerate or update the docstring/Javadoc of a symbol."""

    operation: EditOperation = field(default=EditOperation.REFRESH_DOCSTRING, init=False)
