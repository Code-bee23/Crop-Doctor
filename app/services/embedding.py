import re
import hashlib
from typing import List
import numpy as np


class EmbeddingService:
    """
    Deterministic, high-precision embedding engine for agricultural text chunks.
    Produces L2-normalized 1536-dimensional dense embedding vectors compatible
    with pgvector(1536) in PostgreSQL/Supabase.
    
    Uses SHA-256 deterministic token hashing with subword and domain keyword boosting.
    """
    def __init__(self, dimension: int = 1536):
        self.dimension = dimension

    def _clean_tokens(self, text: str) -> List[str]:
        # Lowercase and extract alphanumeric words
        words = re.findall(r"\b[a-zA-Z0-9_\-\.\%]+\b", text.lower())
        tokens = []
        for i, w in enumerate(words):
            tokens.append(w)
            # Add bigrams for compound phrases (e.g. 'leaf curl', 'pink bollworm', 'brown spot')
            if i < len(words) - 1:
                tokens.append(f"{w}_{words[i+1]}")
            # Add character n-grams for root matching
            if len(w) > 4:
                tokens.append(w[:4])
                tokens.append(w[-4:])
        return tokens

    def _hash_token(self, token: str) -> int:
        """Deterministic integer hash across all Python processes and machines."""
        h = hashlib.sha256(token.encode("utf-8")).digest()
        return int.from_bytes(h[:4], "little") % self.dimension

    def get_embedding(self, text: str) -> List[float]:
        """
        Generate a normalized 1536-dimensional vector for a text query or chunk.
        """
        tokens = self._clean_tokens(text)
        if not tokens:
            return [0.0] * self.dimension

        vector = np.zeros(self.dimension, dtype=np.float32)

        # Domain term weights to boost critical agricultural keywords
        boosts = {
            "whitefly": 5.0, "curling": 4.0, "curl": 4.0, "leaf_curl": 6.0,
            "tella": 4.0, "doma": 4.0, "tella_doma": 7.0,
            "bollworm": 5.0, "pink": 4.0, "pink_bollworm": 6.0,
            "gulabi": 4.0, "aali": 4.0, "gulabi_aali": 7.0, "rosette": 4.0,
            "brown": 4.0, "spot": 4.0, "brown_spot": 6.0,
            "bhoore": 4.0, "dhabbe": 4.0, "bhoore_dhabbe": 7.0,
            "blast": 5.0, "rice_blast": 6.0,
            "nitrogen": 5.0, "yellowing": 4.0, "deficiency": 4.0, "chlorosis": 5.0,
            "pasupu": 4.0,
            "aphid": 5.0, "aphids": 5.0, "mava": 5.0, "thrips": 5.0,
            "chilli": 3.0, "cotton": 3.0, "paddy": 3.0, "tomato": 3.0
        }

        for token in tokens:
            weight = boosts.get(token, 1.0)
            idx = self._hash_token(token)
            vector[idx] += float(weight)

        # L2 Normalization (unit vector for cosine similarity)
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm

        return vector.tolist()

    @staticmethod
    def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two unit vectors."""
        v1 = np.array(vec1, dtype=np.float32)
        v2 = np.array(vec2, dtype=np.float32)
        dot = float(np.dot(v1, v2))
        return float(max(0.0, min(1.0, dot)))


embedding_service = EmbeddingService(dimension=1536)
