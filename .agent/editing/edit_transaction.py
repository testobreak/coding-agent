# editing/edit_transaction.py
#
# Evolved git-backed transaction wrapper for AST symbol-centric modifications.

from execution.modification_transaction import ModificationTransaction

class EditTransaction(ModificationTransaction):
    """
    AST symbol-centric transaction wrapper. Reuses the robust Git-backed 
    Multi-Stage Modification Transaction & Rollback Manager.
    """
    pass
