import hashlib
import math
import re


class EmbeddingBuilder:

    model_name = "local-hash-v1"
    dimensions = 64

    def build(
        self,
        text: str
    ) -> list[float]:

        vector = [0.0] * self.dimensions

        for token in self._tokens(text):
            digest = hashlib.sha256(
                token.encode("utf-8")
            ).digest()
            index = int.from_bytes(
                digest[:2],
                "big"
            ) % self.dimensions
            sign = 1.0 if digest[2] % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(
            sum(value * value for value in vector)
        )

        if not norm:
            return vector

        return [
            round(value / norm, 6)
            for value in vector
        ]

    def content_hash(
        self,
        text: str
    ) -> str:

        return hashlib.sha256(
            text.encode("utf-8")
        ).hexdigest()

    def _tokens(
        self,
        text: str
    ) -> list[str]:

        return re.findall(
            r"[A-Za-z_][A-Za-z0-9_]*",
            text.lower()
        )
