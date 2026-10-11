# routing/complexity_estimator.py

class ComplexityEstimator:
    """
    Estimates query complexity score to assist in fast-path routing decisions.
    Calculates a score between 0.0 and 1.0 using the following formula:
    complexity_score = file_count * 0.35 + dependency_depth * 0.25 + ambiguity * 0.25 + open_endedness * 0.15
    """
    @staticmethod
    def estimate(query: str, editor_context=None) -> float:
        q = query.lower()
        
        # 1. Estimate file count mentioned or touched
        file_count = 1
        if any(w in q for w in ["multiple files", "across files", "every file", "all files"]):
            file_count = 5
        elif any(w in q for w in ["two files", "both files"]):
            file_count = 2
            
        # 2. Dependency depth based on query topics
        dependency_depth = 1
        if any(w in q for w in ["framework", "architecture", "migration", "database", "maven", "spring"]):
            dependency_depth = 4
            
        # 3. Ambiguity of the prompt (shorter queries are typically more ambiguous/open-ended)
        words = q.split()
        ambiguity = 0.8 if len(words) < 4 else (0.5 if len(words) < 8 else 0.2)
        
        # 4. Open-endedness
        open_endedness = 0.1
        if any(w in q for w in ["explain", "how do i", "understand", "review", "audit", "analyse", "analyze"]):
            open_endedness = 0.8
            
        # Normalize components to [0.0, 1.0] range
        norm_file = min(file_count / 5.0, 1.0)
        norm_dep = min(dependency_depth / 5.0, 1.0)
        
        # Compute complexity score
        complexity_score = (
            norm_file * 0.35 +
            norm_dep * 0.25 +
            ambiguity * 0.25 +
            open_endedness * 0.15
        )
        return complexity_score
