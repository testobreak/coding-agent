# retrieval/workspace_router.py

from typing import List, Optional

def classify_workspace_target(query: str, active_file: Optional[str] = None) -> Optional[List[str]]:
    q = query.lower()
    
    # 1. Detect language / workspace area from query keywords
    is_java = any(x in q for x in ["java", "spring", "backend", "maven", "pom.xml", "hibernate", "jpa", "controller", "service", "repository", "entity", "dto"])
    is_frontend = any(x in q for x in ["typescript", "ts", "tsx", "javascript", "js", "jsx", "react", "frontend", "css", "html", "vite", "package.json", "tailwind", "component"])
    is_python = any(x in q for x in ["python", "py", "pytest", "mcp", "agent", "retrieve", "index", "vector", "embed"])
    is_infra = any(x in q for x in ["docker", "infra", "kubernetes", "compose", "deployment"])
    is_docs = any(x in q for x in ["documentation", "docs", "readme", "markdown", "guide"])

    # 2. If no query keywords matched, look at active file extension/path
    if not (is_java or is_frontend or is_python or is_infra or is_docs) and active_file:
        file_lower = active_file.lower()
        if file_lower.endswith(".java") or "backend/" in file_lower:
            is_java = True
        elif any(file_lower.endswith(ext) for ext in [".ts", ".tsx", ".js", ".jsx", ".css", ".html"]) or "frontend/" in file_lower:
            is_frontend = True
        elif file_lower.endswith(".py") or ".agent/" in file_lower or "repository_intelligence/" in file_lower:
            is_python = True
        elif "infra/" in file_lower or "docker" in file_lower:
            is_infra = True
        elif file_lower.endswith(".md") or "docs/" in file_lower:
            is_docs = True

    # 3. Map to workspace roots (matching starting paths)
    if is_java:
        return ["backend"]
    elif is_frontend:
        return ["frontend"]
    elif is_python:
        return ["repository_intelligence", ".agent"]
    elif is_infra:
        return ["infra"]
    elif is_docs:
        return ["docs"]

    return None
