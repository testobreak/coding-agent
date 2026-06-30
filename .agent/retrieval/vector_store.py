# retrieval/vector_store.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any

class VectorStore(ABC):

    @abstractmethod
    def add_embeddings(
        self,
        chunk_ids: List[str],
        vectors: List[List[float]],
        chunks: List[Dict[str, Any]]
    ):
        pass

    @abstractmethod
    def search(
        self,
        query_vector: List[float],
        k: int = 50
    ) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def save(
        self,
        file_path: str
    ):
        pass

    @abstractmethod
    def load(
        self,
        file_path: str
    ):
        pass
