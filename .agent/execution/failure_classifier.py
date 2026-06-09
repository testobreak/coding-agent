# execution/failure_classifier.py
#
# FailureClassifier analyzes validation or test issues to categorize failure modes.

class FailureClassifier:
    def classify(self, issue_type: str, message: str) -> str:
        """
        Classifies an error message into a structured category string.
        """
        msg_lower = (message or "").lower()
        
        if issue_type == "SYNTAX_ERROR" or "mismatched braces" in msg_lower or "syntaxerror" in msg_lower:
            return "SYNTAX_ERROR"
            
        if issue_type == "TEST_FAILURE" or "assertionerror" in msg_lower or "expected" in msg_lower:
            return "TEST_REGRESSION"
            
        if "nullpointerexception" in msg_lower or "nonetype" in msg_lower:
            return "NULLABILITY_ERROR"
            
        if "cannot find symbol" in msg_lower or "cannot resolve symbol" in msg_lower or "import" in msg_lower:
            has_capital = any(w[0].isupper() for w in message.split() if w and w[0].isalpha())
            if "import" in msg_lower or "package" in msg_lower or "class" in msg_lower or has_capital:
                return "MISSING_IMPORT"
            return "UNDEFINED_SYMBOL"
            
        # Fallbacks
        if issue_type == "COMPILATION_ERROR":
            return "COMPILATION_FAILURE"
        if issue_type == "LINT_ERROR":
            return "LINT_VIOLATION"
            
        return "UNKNOWN_ERROR"
