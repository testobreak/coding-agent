from enum import Enum

class EditOperation(str, Enum):
    """Enum of supported symbol‑centric edit actions.

    The values are strings to allow easy JSON serialisation and comparison.
    """
    REPLACE_METHOD_BODY = "replace_method_body"
    ADD_METHOD = "add_method"
    DELETE_METHOD = "delete_method"
    RENAME_SYMBOL = "rename_symbol"
    MOVE_SYMBOL = "move_symbol"
    ADD_IMPORT = "add_import"
    MODIFY_SIGNATURE = "modify_signature"
    INSERT_STATEMENT = "insert_statement"
    DELETE_STATEMENT = "delete_statement"
    ADD_ANNOTATION = "add_annotation"
    REMOVE_ANNOTATION = "remove_annotation"
    REFRESH_DOCSTRING = "refresh_docstring"
    # Extend with additional operations as needed.
