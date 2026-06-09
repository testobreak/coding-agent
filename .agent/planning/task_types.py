# planning/task_types.py
#
# Constraints on allowable execution task types in Plan Compiler.

from enum import Enum

class TaskType(Enum):
    MODIFY_SYMBOL = "modify_symbol"
    CREATE_SYMBOL = "create_symbol"
    DELETE_SYMBOL = "delete_symbol"
    UPDATE_TEST = "update_test"
    RUN_TEST = "run_test"
    VERIFY_BUILD = "verify_build"
    VERIFY_TESTS = "verify_tests"
    VERIFY_LINT = "verify_lint"
    REFORMAT_FILE = "reformat_file"
    
    # Failure handling and transactional types
    ANALYZE_FAILURE = "analyze_failure"
    REPAIR_FAILURE = "repair_failure"
    REPAIR_SYMBOL = "repair_symbol"
    REPAIR_IMPORTS = "repair_imports"
    REPAIR_COMPILATION = "repair_compilation"
    COMMIT_TRANSACTION = "commit_transaction"
    VERIFY_CHANGES = "verify_changes"  # Keep for compatibility with existing code if needed
