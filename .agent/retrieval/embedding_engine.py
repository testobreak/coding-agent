from sentence_transformers import SentenceTransformer
import numpy as np
import time


class EmbeddingEngine:

    def __init__(self):

        print("[Embedding] Loading model...")

        start = time.time()

        self.model = SentenceTransformer(
            "all-MiniLM-L6-v2"
        )

        end = time.time()

        print(
            f"[Embedding] Model loaded "
            f"in {end - start:.2f}s"
        )

    def embed_text(self, text):

        embedding = self.model.encode(
            text,
            convert_to_numpy=True,
            normalize_embeddings=True
        )

        return embedding.astype(np.float32)

    def embed_batch(self, texts, batch_size=32):

        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=True
        )

        return embeddings.astype(np.float32)
