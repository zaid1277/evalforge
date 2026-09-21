import pytest

from app.config import Settings
from app.providers.base import ChunkInput, ProviderConfigError, ProviderResponseError
from app.providers.factory import get_llm_provider
from app.providers.gemini_provider import GeminiProvider
from app.providers.mock_provider import MockProvider


def _chunks():
    return [
        ChunkInput(id=1, text="Employees receive 25 days of annual leave per year."),
        ChunkInput(id=2, text="Employees with five years of service receive five extra days."),
    ]


def test_mock_provider_returns_deterministic_cases():
    provider = MockProvider()

    first = provider.generate_eval_cases(_chunks(), count=5, difficulty="mixed", test_types=["direct"])
    second = provider.generate_eval_cases(_chunks(), count=5, difficulty="mixed", test_types=["direct"])

    assert first == second
    assert len(first) == 5


def test_mock_provider_respects_requested_schema():
    provider = MockProvider()
    chunks = _chunks()
    valid_ids = {c.id for c in chunks}

    cases = provider.generate_eval_cases(
        chunks, count=6, difficulty="mixed", test_types=["direct", "multi_step", "unanswerable"]
    )

    assert len(cases) == 6
    for case in cases:
        assert case.test_type.value in {"direct", "multi_step", "unanswerable"}
        assert case.difficulty.value in {"easy", "medium"}
        assert set(case.source_chunk_ids) <= valid_ids


def test_provider_selection_chooses_mock_when_configured():
    settings = Settings(USE_MOCK_LLM=True, LLM_PROVIDER="gemini", GEMINI_API_KEY="")
    provider = get_llm_provider(settings)
    assert isinstance(provider, MockProvider)


def test_provider_selection_chooses_gemini_when_configured():
    settings = Settings(USE_MOCK_LLM=False, LLM_PROVIDER="gemini", GEMINI_API_KEY="fake-key-for-test")
    provider = get_llm_provider(settings)
    assert isinstance(provider, GeminiProvider)


def test_missing_gemini_key_is_handled_cleanly():
    settings = Settings(USE_MOCK_LLM=False, LLM_PROVIDER="gemini", GEMINI_API_KEY="")

    with pytest.raises(ProviderConfigError, match="Gemini API key is not configured"):
        get_llm_provider(settings)


# --- M9: MockProvider evaluation behavior --------------------------------


def test_mock_generate_response_is_deterministic():
    provider = MockProvider()
    question = "What does the source say about 'Employees receive 25 days'?"

    first = provider.generate_response(question)
    second = provider.generate_response(question)

    assert first == second


def test_mock_generate_response_recognizes_unanswerable_style_question():
    provider = MockProvider()
    question = "What does the source not say about 'Employees receive 25 days'?"

    response = provider.generate_response(question)

    assert response == "The provided information does not specify this."


def test_mock_judge_passes_refusal_style_response():
    provider = MockProvider()

    result = provider.judge_unanswerable_response(
        question="What is the CEO's favorite color?",
        model_response="The provided information does not specify this.",
    )

    assert result.passed is True
    assert result.reason


def test_mock_judge_fails_fabricated_response():
    provider = MockProvider()

    result = provider.judge_unanswerable_response(
        question="What is the CEO's favorite color?",
        model_response="The CEO's favorite color is blue.",
    )

    assert result.passed is False
    assert result.reason


# --- M9: GeminiProvider judge-output parsing -------------------------------
#
# These exercise only the JSON-parsing/Pydantic-validation boundary
# (_parse_judge_result), never the network call itself -- no API key is
# used to reach Gemini, only a fake one to construct the client (the same
# pattern test_provider_selection_chooses_gemini_when_configured already
# relies on: constructing a genai.Client does not itself make a network
# call or validate the key).


def _gemini_provider():
    return GeminiProvider(api_key="fake-key-for-test", model="fake-model")


def test_gemini_parse_judge_result_valid_json():
    provider = _gemini_provider()

    result = provider._parse_judge_result('{"pass": true, "reason": "acknowledges the gap"}')

    assert result.passed is True
    assert result.reason == "acknowledges the gap"


def test_gemini_parse_judge_result_invalid_json_raises():
    provider = _gemini_provider()

    with pytest.raises(ProviderResponseError, match="invalid JSON"):
        provider._parse_judge_result("not json at all")


def test_gemini_parse_judge_result_schema_violation_raises():
    provider = _gemini_provider()

    with pytest.raises(ProviderResponseError, match="failed validation"):
        provider._parse_judge_result('{"pass": true}')  # missing required "reason"


def test_gemini_parse_judge_result_empty_response_raises():
    provider = _gemini_provider()

    with pytest.raises(ProviderResponseError, match="empty response"):
        provider._parse_judge_result(None)
