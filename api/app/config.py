"""
Application configuration.

All settings are loaded from environment variables (optionally via a local
.env file during development). Nothing here should ever contain a real
secret -- values are placeholders/defaults, and actual keys are supplied
through the environment at runtime.
"""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- General ---
    APP_NAME: str = "EvalForge API"
    ENVIRONMENT: str = "development"

    # --- Database ---
    # Example: postgresql+psycopg2://user:password@localhost:5432/evalforge
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/evalforge"

    # --- LLM Provider ---
    # Only Gemini is required for the MVP. These settings are read now so
    # the rest of the app can be wired up, but no provider code calls the
    # live API until the Generation milestone (M4).
    LLM_PROVIDER: str = "gemini"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.1-flash-lite"

    # When true, the app should use deterministic fixture responses instead
    # of calling any external LLM API. Not used yet in M0.
    USE_MOCK_LLM: bool = False

    # --- Generation / evaluation batch safety limits (used from M4 onward) ---
    MAX_GENERATION_CASES: int = 50
    MAX_EVALUATION_CASES: int = 50

    # --- Source uploads ---
    # Applies to both file uploads and pasted text, so nothing oversized
    # ends up stored in the database. Whole files are read into memory
    # (no streaming/object storage), so this also bounds memory use.
    MAX_UPLOAD_SIZE_MB: int = 10

    # --- Source chunking ---
    # A chunk grows paragraph by paragraph until adding the next paragraph
    # would push it past CHUNK_TARGET_WORDS. CHUNK_MAX_WORDS is the ceiling
    # used to decide when a single paragraph is "oversized" and needs to be
    # split on its own (see chunking_service.py).
    CHUNK_TARGET_WORDS: int = 750
    CHUNK_MAX_WORDS: int = 1000

    # --- Embeddings / semantic duplicate detection (M6) ---
    # Runs locally via sentence-transformers -- no API key, no Gemini call.
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    # Cosine similarity >= this value flags a question as a possible
    # duplicate of another question in the same project. A heuristic, not
    # proof -- see services/duplicate_service.py.
    DUPLICATE_SIMILARITY_THRESHOLD: float = 0.90

    @field_validator("DUPLICATE_SIMILARITY_THRESHOLD")
    @classmethod
    def _validate_duplicate_threshold(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("DUPLICATE_SIMILARITY_THRESHOLD must be between 0.0 and 1.0")
        return value

    # --- Grounding heuristic (M7) ---
    # Cosine similarity between a reference answer and its exact linked
    # source evidence, below which a case is flagged "review grounding".
    # Lower than the duplicate threshold by design: a correct answer is
    # usually *paraphrased* from its evidence (different wording, same
    # meaning), so answer-to-evidence similarity is naturally lower than
    # near-duplicate question-to-question similarity.
    #
    # 0.40 rather than the initially suggested 0.30, based on real MiniLM
    # measurements taken while building this feature: clearly-unrelated
    # pairs scored ~0.24-0.33, while genuinely-related pairs scored ~0.50
    # and up (including a terse-but-correct answer like "25 days."). 0.40
    # sits in that gap. Note a real limitation this surfaced: a same-topic
    # but factually-wrong answer ("a company car" vs. "25 days of leave")
    # scored ~0.45 -- *above* this threshold, so it would NOT be flagged.
    # That's an inherent limit of semantic similarity (it measures topical
    # relatedness, not fact-checking), not something raising the threshold
    # further can fix without flagging legitimate terse answers instead.
    # See the M7 completion report for the full measured table. Still just
    # a heuristic, still fully configurable, and not tuned to force one
    # specific demo case to pass.
    GROUNDING_SIMILARITY_THRESHOLD: float = 0.40

    @field_validator("GROUNDING_SIMILARITY_THRESHOLD")
    @classmethod
    def _validate_grounding_threshold(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("GROUNDING_SIMILARITY_THRESHOLD must be between 0.0 and 1.0")
        return value

    # --- Model evaluation (M9) ---
    # Cosine similarity between a target model's response and the case's
    # reference_answer, at or above which an *answerable* case is scored
    # "passed". Reuses the same MiniLM model/cosine_similarity as M6/M7 --
    # no second embedding model.
    #
    # Kept at the PRD-suggested 0.75 based on real MiniLM measurements
    # (see the M9 completion report for the full table):
    #   reference vs. a differently-worded correct answer    -> 0.9428
    #   reference vs. a genuinely unrelated answer            -> 0.3598
    #   reference vs. a same-topic answer with a wrong number -> 0.9208
    #   reference vs. a terse-but-correct fragment ("25 days.") -> 0.5057
    # 0.75 sits well inside the wide gap between similar (0.94) and
    # unrelated (0.36) full-sentence answers. Two known limitations this
    # surfaced, same family as GROUNDING_SIMILARITY_THRESHOLD's: (1) it
    # does NOT catch a factually-wrong answer that keeps the same wording
    # and topic (0.9208, above threshold -- semantic similarity measures
    # topical relatedness, not fact-checking); (2) a very terse-but-correct
    # response can score below threshold and be marked "failed" even
    # though it's right, since it shares less wording with a full-sentence
    # reference_answer. Not tuned to force either case to pass -- both are
    # reported honestly rather than adjusting the threshold to hide them.
    ANSWER_SIMILARITY_THRESHOLD: float = 0.75

    @field_validator("ANSWER_SIMILARITY_THRESHOLD")
    @classmethod
    def _validate_answer_threshold(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("ANSWER_SIMILARITY_THRESHOLD must be between 0.0 and 1.0")
        return value

    # --- CORS ---
    # Comma-separated list of origins allowed to call the API from the browser.
    CORS_ORIGINS: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024


# Single shared settings instance, imported wherever configuration is needed.
settings = Settings()
