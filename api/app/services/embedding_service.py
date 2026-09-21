"""
Text embeddings for semantic duplicate detection (M6).

An embedding turns a piece of text into a vector of numbers, positioned
so that texts with similar *meaning* end up pointing in similar
directions -- even when the wording is completely different. That's what
lets us notice that "How many annual leave days do employees receive?"
and "What is the employee annual leave entitlement?" are asking almost
the same thing, despite sharing very few exact words.

Model: all-MiniLM-L6-v2, via the sentence-transformers library. It turns
a sentence into a 384-dimensional vector. It's small, runs on CPU in a
fraction of a second, needs no API key, and makes no network call once
downloaded -- a good fit for a locally-run student project.

Important: an embedding captures approximate semantic *meaning*, not
factual correctness. A high similarity score is a heuristic hint for a
human reviewer, never proof that two questions are duplicates.
"""

from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import settings


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    """Load the MiniLM model once and reuse it for the life of the process.

    This only runs the first time it's called (i.e. the first time
    duplicate detection actually runs), not at app startup -- so the rest
    of EvalForge keeps working even before the model has been downloaded
    or loaded.
    """
    return SentenceTransformer(settings.EMBEDDING_MODEL)


def embed_texts(texts: list[str]) -> np.ndarray:
    """Encode many texts in a single batched model call.

    Calling the model once with a list of texts is far cheaper than
    calling it once per text, and is exactly what sentence-transformers
    is built for. Returns an (n, 384) array, one row per input text.
    """
    if not texts:
        return np.empty((0, 0))
    model = get_embedding_model()
    return np.asarray(model.encode(list(texts)))


def cosine_similarity(vector_a: np.ndarray, vector_b: np.ndarray) -> float:
    """cosine_similarity(A, B) = (A . B) / (||A|| * ||B||)

    The dot product (A . B) measures how much two vectors point in the
    same direction. Dividing by the product of their lengths (||A|| and
    ||B||) removes the effect of vector magnitude, leaving a score
    between -1 and 1:

        1.0  -> pointing in exactly the same direction (very similar meaning)
        0.0  -> unrelated / orthogonal
       -1.0  -> pointing in opposite directions

    In practice, real sentence embeddings for ordinary English text are
    almost always positive.
    """
    norm_a = float(np.linalg.norm(vector_a))
    norm_b = float(np.linalg.norm(vector_b))
    if norm_a == 0.0 or norm_b == 0.0:
        # A zero vector has no direction to compare against -- treat it as
        # unrelated instead of dividing by zero.
        return 0.0
    return float(np.dot(vector_a, vector_b) / (norm_a * norm_b))
