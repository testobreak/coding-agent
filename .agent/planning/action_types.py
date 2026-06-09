# planning/action_types.py

# =========================================================
# REPOSITORY UNDERSTANDING
# =========================================================

RETRIEVE = "retrieve"

READ_FILE = "read_file"

ANALYZE = "analyze"

SUMMARIZE = "summarize"


# =========================================================
# MODIFICATION
# =========================================================

MODIFICATION_PLANNING = (
    "modification_planning"
)

MODIFY = "modify"

PATCH = "patch"

GENERATE_MODIFICATION = (
    "generate_modification"
)

GENERATE_PATCH = (
    "generate_patch"
)

WRITE_FILE = "write_file"

VALIDATE = "validate"


# =========================================================
# TESTING
# =========================================================

TEST = "test"

RUN_BACKEND_TESTS = (
    "run_backend_tests"
)

RUN_FRONTEND_TESTS = (
    "run_frontend_tests"
)

RUN_FRONTEND_BUILD = (
    "run_frontend_build"
)


# =========================================================
# GIT / SAFETY
# =========================================================

GIT_STATUS = "git_status"

GIT_DIFF = "git_diff"

ROLLBACK = "rollback"

COMMIT = "commit"


# =========================================================
# RECOVERY / REFLECTION
# =========================================================

REPAIR = "repair"

REFLECT = "reflect"

REPLAN = "replan"


# =========================================================
# TASK TYPES
# =========================================================

BUG_FIX = "bug_fix"

FEATURE = "feature"

REFACTOR = "refactor"

ANALYSIS = "analysis"

UNKNOWN = "unknown"
