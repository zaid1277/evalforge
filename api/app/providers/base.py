"""
Provider abstraction for LLM-backed evaluation-case generation (M4) and
model evaluation (M9).

generation_service.py and evaluation_service.py talk only to this
interface -- neither calls Gemini (or any other provider) directly.
That's what lets MockProvider stand in during tests and local UI
development without touching a real API, and lets a future provider be
added without changing either service's logic at all.

Generation and evaluation are kept as separate methods on purpose, even
though both ultimately call an LLM: generation turns source evidence
into questions (generate_eval_cases), evaluation turns a question into a
target model's answer (generate_response) and, for unanswerable cases,
judges that answer (judge_unanswerable_response). Reusing the generation
prompt for evaluation would conflate two different tasks.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.schemas.generation import GeneratedCase


@dataclass
class ChunkInput:
    """A minimal, provider-agnostic view of one source chunk. Keeps
    providers decoupled from the SQLAlchemy SourceChunk model."""

    id: int
    text: str


@dataclass
class JudgeResult:
    """The outcome of judging whether a target model's response to an
    *unanswerable* question appropriately acknowledges missing
    information, rather than inventing an answer (see M9)."""

    passed: bool
    reason: str


class ProviderError(Exception):
    """Base class for provider failures."""


class ProviderConfigError(ProviderError):
    """The provider is misconfigured, e.g. a missing API key."""


class ProviderResponseError(ProviderError):
    """The provider's response could not be parsed/validated (into
    GeneratedCase objects, or -- for M9 -- a JudgeResult). Callers retry
    at most once on this specific error, since it may just be LLM
    non-determinism."""


class LLMProvider(ABC):
    @abstractmethod
    def generate_eval_cases(
        self,
        chunks: list[ChunkInput],
        count: int,
        difficulty: str,
        test_types: list[str],
    ) -> list[GeneratedCase]:
        """Generate up to `count` evaluation cases grounded only in `chunks`.

        Must raise ProviderResponseError if the provider's output can't be
        parsed or validated -- callers depend on that specific exception
        type for retry logic.
        """

    @abstractmethod
    def generate_response(self, question: str) -> str:
        """Answer `question` as the target model under evaluation (M9).

        The caller (evaluation_service.py) must never pass the case's
        reference_answer, duplicate_score, grounding_score, or review
        status here -- only the bare question, so the model answers
        independently instead of having the answer leaked to it.

        Must raise ProviderResponseError if the request fails.
        """

    @abstractmethod
    def judge_unanswerable_response(self, question: str, model_response: str) -> JudgeResult:
        """Judge whether `model_response` appropriately acknowledges that
        `question` cannot be answered, rather than inventing information
        (M9, used only for is_answerable=False cases).

        Conceptually a separate role from generate_response even though
        Gemini's implementation may call the same underlying model for
        both -- this judges model_response, it never regenerates or
        grades an answer against a fabricated reference.

        Must raise ProviderResponseError if the judge's output can't be
        parsed or validated -- callers depend on that specific exception
        type for retry logic.
        """
