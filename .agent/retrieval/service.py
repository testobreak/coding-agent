# retrieval/service.py
import os
import atexit
from typing import List, Dict, Any, Optional
from retrieval.retrieval_pipeline import RetrievalPipeline
from retrieval.retriever import CodeRetriever

def resolve_repo_root() -> str:
    """
    Robustly resolves the project repository root directory.
    Walks up from the current directory to find the folder containing '.agent'.
    """
    cwd = os.getcwd()
    # Check if currently inside .agent directory
    if os.path.basename(cwd) == ".agent":
        return os.path.dirname(cwd)
    # Check if .agent exists in current directory
    if os.path.exists(os.path.join(cwd, ".agent")):
        return cwd
    # Traverse parents
    curr = cwd
    while True:
        if os.path.exists(os.path.join(curr, ".agent")):
            return curr
        parent = os.path.dirname(curr)
        if parent == curr:
            break
        curr = parent
    return cwd


class RetrievalFacade:
    _instance = None

    @classmethod
    def get_instance(cls, repo_root: str = None, model_service=None) -> "RetrievalFacade":
        """
        Return (or create) the singleton RetrievalFacade.

        Parameters
        ----------
        repo_root : str, optional
            Repository root. Resolved automatically if not provided.
        model_service : ModelService, optional
            Shared model service from Runtime. If provided, CodeRetriever
            will use the already-loaded embedding model — no duplicate load.
        """
        if not cls._instance:
            cls._instance = super(RetrievalFacade, cls).__new__(cls)
            repo_root = repo_root or resolve_repo_root()
            cls._instance.retriever = CodeRetriever(
                repo_root=repo_root,
                model_service=model_service
            )
            cls._instance.pipeline = RetrievalPipeline(cls._instance.retriever)
            atexit.register(cls._instance.close)
        return cls._instance

    def __new__(cls, *args, **kwargs):
        # Legacy support: direct instantiation still works, but model_service
        # won't be injected through this path.
        if not cls._instance:
            cls._instance = super(RetrievalFacade, cls).__new__(cls)
            repo_root = resolve_repo_root()
            cls._instance.retriever = CodeRetriever(repo_root=repo_root)
            cls._instance.pipeline = RetrievalPipeline(cls._instance.retriever)
            atexit.register(cls._instance.close)
        return cls._instance


    def close(self):
        """Terminates active pgvector background pool threads cleanly."""
        if hasattr(self, "retriever") and self.retriever:
            if hasattr(self.retriever, "pgvector_backend") and self.retriever.pgvector_backend:
                try:
                    self.retriever.pgvector_backend.close()
                except Exception:
                    pass

    def retrieve(self, query: str, context: Optional[Any] = None, top_k: int = 10) -> List[Dict[str, Any]]:
        """Unified, single retrieval entrypoint for the entire system."""
        return self.pipeline.retrieve(query, context=context, top_k=top_k)
