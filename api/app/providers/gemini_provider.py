"""
Google Gemini provider.

Calls the Gemini API directly through Google's official `google-genai`
SDK -- no LangChain/LlamaIndex/agent framework in between. The model
identifier always comes from configuration (GEMINI_MODEL); it is never
hard-coded here, so it can be changed without touching this file.
"""

import json
import logging

from google import genai
from google.genai import types
from pydantic import ValidationError

from app.providers.base import ChunkInput, JudgeResult, LLMProvider, ProviderResponseError
from app.providers.prompts import build_evaluation_prompt, build_generation_prompt, build_judge_prompt
from app.schemas.evaluation import JudgeVerdict
from app.schemas.generation import GeneratedCase

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        # The API key is only ever read from configuration by the caller
        # (see providers/factory.py) and passed in here -- never logged,
        # never returned in a response, never sent to the frontend.
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def generate_eval_cases(
        self,
        chunks: list[ChunkInput],
        count: int,
        difficulty: str,
        test_types: list[str],
    ) -> list[GeneratedCase]:
        prompt = build_generation_prompt(chunks, count, difficulty, test_types)

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
        except Exception as exc:  # SDK network/auth/API errors of various types
            raise ProviderResponseError(f"Gemini request failed: {exc}") from exc

        return self._parse_cases(response.text)

    def _parse_cases(self, raw_text: str | None) -> list[GeneratedCase]:
        if not raw_text:
            raise ProviderResponseError("Gemini returned an empty response.")

        try:
            raw_items = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ProviderResponseError(f"Gemini returned invalid JSON: {exc}") from exc

        if not isinstance(raw_items, list):
            raise ProviderResponseError("Gemini response was not a JSON array of cases.")

        cases: list[GeneratedCase] = []
        for item in raw_items:
            try:
                cases.append(GeneratedCase.model_validate(item))
            except ValidationError as exc:
                raise ProviderResponseError(
                    f"Gemini returned a case that failed validation: {exc}"
                ) from exc

        return cases

    def generate_response(self, question: str) -> str:
        """M9: answer `question` as the target model under evaluation.
        Plain-text response, not structured JSON -- see
        build_evaluation_prompt (providers/prompts.py) for exactly what
        is (and is not) sent."""
        prompt = build_evaluation_prompt(question)

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
            )
        except Exception as exc:  # SDK network/auth/API errors of various types
            raise ProviderResponseError(f"Gemini request failed: {exc}") from exc

        if not response.text:
            raise ProviderResponseError("Gemini returned an empty response.")
        return response.text.strip()

    def judge_unanswerable_response(self, question: str, model_response: str) -> JudgeResult:
        """M9: structured-JSON judge call for an unanswerable case's
        response. Uses the same Gemini model as generate_response above
        (see the "Judge Separation" note in providers/base.py) but a
        completely different, centralized prompt (build_judge_prompt) and
        a strict Pydantic-validated response shape (JudgeVerdict)."""
        prompt = build_judge_prompt(question, model_response)

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
        except Exception as exc:
            raise ProviderResponseError(f"Gemini judge request failed: {exc}") from exc

        return self._parse_judge_result(response.text)

    def _parse_judge_result(self, raw_text: str | None) -> JudgeResult:
        if not raw_text:
            raise ProviderResponseError("Gemini judge returned an empty response.")

        try:
            raw_data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ProviderResponseError(f"Gemini judge returned invalid JSON: {exc}") from exc

        try:
            verdict = JudgeVerdict.model_validate(raw_data)
        except ValidationError as exc:
            raise ProviderResponseError(f"Gemini judge output failed validation: {exc}") from exc

        return JudgeResult(passed=verdict.passed, reason=verdict.reason)
