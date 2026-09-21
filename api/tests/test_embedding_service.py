"""
Unit tests for the cosine similarity math (fast, no model involved), plus
one real-MiniLM smoke test that's excluded from the default test run (see
pytest.ini) since it downloads/loads an actual model. Run it explicitly
with:

    pytest -m real_model tests/test_embedding_service.py -v
"""

import numpy as np
import pytest

from app.services.embedding_service import cosine_similarity, embed_texts


def test_identical_vectors_have_similarity_one():
    vector = np.array([1.0, 2.0, 3.0])
    assert cosine_similarity(vector, vector) == pytest.approx(1.0)


def test_orthogonal_vectors_have_similarity_zero():
    a = np.array([1.0, 0.0])
    b = np.array([0.0, 1.0])
    assert cosine_similarity(a, b) == pytest.approx(0.0)


def test_opposite_vectors_have_similarity_negative_one():
    a = np.array([1.0, 0.5])
    b = np.array([-1.0, -0.5])
    assert cosine_similarity(a, b) == pytest.approx(-1.0)


def test_similar_vectors_score_higher_than_unrelated_ones():
    anchor = np.array([1.0, 2.0, 3.0])
    similar = np.array([1.1, 2.1, 2.9])
    unrelated = np.array([-3.0, 1.0, -0.5])

    assert cosine_similarity(anchor, similar) > cosine_similarity(anchor, unrelated)


def test_zero_vector_does_not_crash():
    zero = np.array([0.0, 0.0, 0.0])
    other = np.array([1.0, 2.0, 3.0])

    assert cosine_similarity(zero, other) == 0.0
    assert cosine_similarity(zero, zero) == 0.0


def test_embed_texts_returns_empty_array_for_empty_input():
    result = embed_texts([])
    assert len(result) == 0


@pytest.mark.real_model
def test_real_minilm_similar_questions_score_higher_than_unrelated():
    """One real, non-mocked run of all-MiniLM-L6-v2 (see PRD M6 'Manual
    Real MiniLM Verification'). Downloads/caches the model locally on
    first run -- no API key involved."""
    question_a = "How many annual leave days do employees receive?"
    question_b = "What is the employee annual leave entitlement?"
    question_c = "What is the company policy on remote-work equipment?"

    vectors = embed_texts([question_a, question_b, question_c])
    similarity_ab = cosine_similarity(vectors[0], vectors[1])
    similarity_ac = cosine_similarity(vectors[0], vectors[2])

    print(f"\nsimilarity(A, B) = {similarity_ab:.4f}")
    print(f"similarity(A, C) = {similarity_ac:.4f}")

    assert similarity_ab > similarity_ac
