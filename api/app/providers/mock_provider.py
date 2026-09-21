"""
Deterministic fixture provider.

Used for local UI development without API quota, and for every automated
test -- no test in this project ever calls a real LLM. Given the same
inputs, this always returns the same output (no randomness), which is
exactly what makes it useful for repeatable tests.
"""

import hashlib
import re

from app.models.evaluation_case import TestType
from app.providers.base import ChunkInput, JudgeResult, LLMProvider
from app.schemas.generation import MAX_MULTI_STEP_CHUNKS, GeneratedCase

# Substring MockProvider's own generate_eval_cases uses when phrasing an
# unanswerable question (see _build_case below) -- generate_response
# looks for this same phrase to decide how to "answer" a question,
# without ever being told the case's real test_type/is_answerable (M9
# evaluation only ever sends the bare question, matching what a real
# target model would receive).
_UNANSWERABLE_PHRASE = "not say about"
_UNANSWERABLE_STYLE_RESPONSE = "The provided information does not specify this."

# Phrases a mock "refuses to guess" response might use -- checked by
# judge_unanswerable_response below. Deliberately broader than just the
# exact phrase generate_response produces, so a hand-crafted test
# response like "I don't know" or "cannot be determined" is still
# recognized as an appropriate refusal.
_REFUSAL_MARKERS = (
    "does not specify",
    "cannot be determined",
    "cannot determine",
    "not available",
    "not provided",
    "don't have",
    "do not have",
    "no information",
    "unknown",
)


class MockProvider(LLMProvider):
    def generate_eval_cases(
        self,
        chunks: list[ChunkInput],
        count: int,
        difficulty: str,
        test_types: list[str],
    ) -> list[GeneratedCase]:
        if not chunks or count <= 0:
            return []

        difficulties = ["easy", "medium"] if difficulty == "mixed" else [difficulty]

        cases: list[GeneratedCase] = []
        for i in range(count):
            test_type = test_types[i % len(test_types)]
            chunk = chunks[i % len(chunks)]
            case_difficulty = difficulties[i % len(difficulties)]
            cases.append(
                self._build_case(i, test_type, chunk, chunks, case_difficulty)
            )
        return cases

    def generate_response(self, question: str) -> str:
        """Deterministic mock answer, derived only from `question` text --
        never told the case's real test_type/reference_answer, exactly
        like a real target model under evaluation (M9).

        Recognizes MockProvider's own "what does the source not say
        about '...'" phrasing (see _build_case) and mimics a model that
        correctly declines to guess. For every other question, it
        deterministically answers with the quoted snippet for roughly
        half of all questions (a "correct-shaped" answer) and a generic
        non-answer for the other half, based on a hash of the question
        text -- not randomness, but enough variety that a mock evaluation
        run exercises both pass and fail paths.
        """
        if _UNANSWERABLE_PHRASE in question:
            return _UNANSWERABLE_STYLE_RESPONSE

        snippet_match = re.search(r"'([^']*)'", question)
        snippet = snippet_match.group(1) if snippet_match else question

        digest = hashlib.md5(question.encode()).digest()
        if digest[0] % 2 == 0:
            return f"[Mock response] {snippet}"
        return "[Mock response] I don't have information about that."

    def judge_unanswerable_response(self, question: str, model_response: str) -> JudgeResult:
        """Deterministic stand-in for the Gemini judge (M9): passes when
        model_response contains a recognizable refusal/unknown-style
        phrase, fails when it confidently states something instead --
        the same rubric given to the real judge prompt
        (providers/prompts.py's build_judge_prompt), just pattern-matched
        instead of asked of an LLM."""
        lowered = model_response.lower()
        if any(marker in lowered for marker in _REFUSAL_MARKERS):
            return JudgeResult(
                passed=True,
                reason="Mock judge: response acknowledges the information is unavailable.",
            )
        return JudgeResult(
            passed=False,
            reason="Mock judge: response does not acknowledge missing information.",
        )

    def _build_case(
        self,
        index: int,
        test_type: str,
        chunk: ChunkInput,
        all_chunks: list[ChunkInput],
        difficulty: str,
    ) -> GeneratedCase:
        snippet = chunk.text[:40].strip()

        if test_type == TestType.UNANSWERABLE.value:
            return GeneratedCase(
                question=f"[Mock {index + 1}] What does the source not say about '{snippet}'?",
                reference_answer=None,
                source_chunk_ids=[chunk.id],
                category="general",
                difficulty=difficulty,
                test_type=TestType.UNANSWERABLE,
                is_answerable=False,
            )

        if test_type == TestType.MULTI_STEP.value:
            second_chunk = all_chunks[(index + 1) % len(all_chunks)]
            chunk_ids = sorted({chunk.id, second_chunk.id})[:MAX_MULTI_STEP_CHUNKS]
            return GeneratedCase(
                question=f"[Mock {index + 1}] Combining source details, what follows from '{snippet}'?",
                reference_answer=f"[Mock {index + 1}] Answer derived from the supplied source chunks.",
                source_chunk_ids=chunk_ids,
                category="general",
                difficulty=difficulty,
                test_type=TestType.MULTI_STEP,
                is_answerable=True,
            )

        # direct
        return GeneratedCase(
            question=f"[Mock {index + 1}] What does the source say about '{snippet}'?",
            reference_answer=f"[Mock {index + 1}] {snippet}",
            source_chunk_ids=[chunk.id],
            category="general",
            difficulty=difficulty,
            test_type=TestType.DIRECT,
            is_answerable=True,
        )
