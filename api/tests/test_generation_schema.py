import pytest
from pydantic import ValidationError

from app.schemas.generation import GeneratedCase


def _base(**overrides):
    data = dict(
        question="How many days of annual leave are provided?",
        reference_answer="Employees receive 25 days of annual leave per year.",
        source_chunk_ids=[1],
        category="employee_benefits",
        difficulty="easy",
        test_type="direct",
        is_answerable=True,
    )
    data.update(overrides)
    return data


def test_valid_direct_case_accepted():
    case = GeneratedCase(**_base())
    assert case.test_type.value == "direct"


def test_valid_multi_step_case_accepted():
    case = GeneratedCase(
        **_base(
            source_chunk_ids=[1, 2],
            test_type="multi_step",
            reference_answer="Combining both facts gives 30 days.",
        )
    )
    assert case.source_chunk_ids == [1, 2]


def test_valid_unanswerable_case_accepted():
    case = GeneratedCase(
        **_base(
            reference_answer=None,
            test_type="unanswerable",
            is_answerable=False,
        )
    )
    assert case.reference_answer is None
    assert case.is_answerable is False


def test_answerable_without_reference_answer_rejected():
    with pytest.raises(ValidationError):
        GeneratedCase(**_base(reference_answer=None))


def test_unanswerable_with_fabricated_reference_answer_rejected():
    with pytest.raises(ValidationError):
        GeneratedCase(
            **_base(
                test_type="unanswerable",
                is_answerable=False,
                reference_answer="A fabricated answer.",
            )
        )


def test_invalid_difficulty_rejected():
    with pytest.raises(ValidationError):
        GeneratedCase(**_base(difficulty="hard"))


def test_invalid_test_type_rejected():
    with pytest.raises(ValidationError):
        GeneratedCase(**_base(test_type="open_ended"))


def test_empty_question_rejected():
    with pytest.raises(ValidationError):
        GeneratedCase(**_base(question="   "))


def test_empty_source_chunk_list_rejected():
    with pytest.raises(ValidationError):
        GeneratedCase(**_base(source_chunk_ids=[]))


def test_multi_step_with_more_than_two_chunks_rejected():
    with pytest.raises(ValidationError):
        GeneratedCase(
            **_base(
                source_chunk_ids=[1, 2, 3],
                test_type="multi_step",
                reference_answer="Answer spanning three chunks.",
            )
        )


def test_test_type_answerability_mismatch_rejected():
    with pytest.raises(ValidationError):
        GeneratedCase(**_base(test_type="direct", is_answerable=False, reference_answer=None))


def test_blank_reference_answer_normalized_to_none():
    case = GeneratedCase(
        **_base(reference_answer="   ", test_type="unanswerable", is_answerable=False)
    )
    assert case.reference_answer is None
