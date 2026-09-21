import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.evaluation_case_source import EvaluationCaseSource
    from app.models.project import Project


def _enum_values(enum_cls):
    """Store/compare a Python enum's lowercase `.value` strings in the
    database, instead of SQLAlchemy's default of using the member *names*
    (see the same note in models/source.py)."""
    return [member.value for member in enum_cls]


class Difficulty(str, enum.Enum):
    """Per-case difficulty. "mixed" is only a generation *request* option
    (see schemas/generation.py) -- every stored case is EASY or MEDIUM."""

    EASY = "easy"
    MEDIUM = "medium"


class TestType(str, enum.Enum):
    DIRECT = "direct"
    MULTI_STEP = "multi_step"
    UNANSWERABLE = "unanswerable"


class EvaluationStatus(str, enum.Enum):
    """M5 adds the review workflow that moves cases out of GENERATED."""

    GENERATED = "generated"
    APPROVED = "approved"
    REJECTED = "rejected"


class EvaluationCase(Base):
    __tablename__ = "evaluation_cases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    question: Mapped[str] = mapped_column(Text, nullable=False)
    # Null for unanswerable cases -- see schemas/generation.py's validation,
    # which is what actually enforces the answerable/unanswerable rules.
    reference_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False)

    difficulty: Mapped[Difficulty] = mapped_column(
        SAEnum(Difficulty, name="eval_case_difficulty", values_callable=_enum_values),
        nullable=False,
    )
    test_type: Mapped[TestType] = mapped_column(
        SAEnum(TestType, name="eval_case_test_type", values_callable=_enum_values),
        nullable=False,
    )
    is_answerable: Mapped[bool] = mapped_column(Boolean, nullable=False)

    status: Mapped[EvaluationStatus] = mapped_column(
        SAEnum(EvaluationStatus, name="eval_case_status", values_callable=_enum_values),
        nullable=False,
        default=EvaluationStatus.GENERATED,
        server_default=EvaluationStatus.GENERATED.value,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Highest cosine similarity (see services/embedding_service.py) between
    # this case's question and any other case's question in the same
    # project. Null until at least one comparison has been made (e.g. the
    # project only has this one case so far). Recomputed by
    # services/duplicate_service.py -- never written directly.
    duplicate_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Cosine similarity (see services/embedding_service.py) between this
    # case's reference_answer and the exact source evidence linked to it
    # via EvaluationCaseSource. Always null for unanswerable cases (there
    # is no reference_answer to compare). A heuristic hint that the
    # answer's wording is semantically related to its evidence -- not a
    # factual-correctness check. Recomputed by services/grounding_service.py.
    grounding_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="evaluation_cases")

    # Deleting a case (future milestone) removes its join-table rows too.
    source_links: Mapped[list["EvaluationCaseSource"]] = relationship(
        back_populates="evaluation_case", cascade="all, delete-orphan"
    )

    @property
    def source_chunk_ids(self) -> list[int]:
        return [link.source_chunk_id for link in self.source_links]
