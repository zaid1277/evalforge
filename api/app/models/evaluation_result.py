from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.evaluation_case import Difficulty, TestType, _enum_values

if TYPE_CHECKING:
    from app.models.evaluation_case import EvaluationCase
    from app.models.evaluation_run import EvaluationRun


class EvaluationResult(Base):
    """One case's outcome within an EvaluationRun (M9).

    Snapshot design (Option B from the PRD): `question_snapshot`,
    `reference_answer_snapshot`, `test_type_snapshot`, and
    `difficulty_snapshot` copy the case's content *as it was at
    evaluation time*, rather than only referencing EvaluationCase and
    reading its current fields. This means a later edit to the case (M5
    review can still edit question/reference_answer/etc. at any time)
    never silently rewrites the meaning of a historical result -- opening
    an old run always shows exactly what was actually evaluated.
    `evaluation_case_id` is kept too, for the relational link back to the
    live case (e.g. so a reviewer can jump to it), but the snapshot
    fields are what the detail view actually displays.

    duplicate_score/grounding_score are deliberately NOT snapshotted here
    -- those are dataset-quality heuristics (M6/M7), a different concern
    from model-evaluation outcome, and are already visible on the case
    itself.
    """

    __tablename__ = "evaluation_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    evaluation_run_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evaluation_case_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )

    question_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    reference_answer_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_type_snapshot: Mapped[TestType] = mapped_column(
        SAEnum(TestType, name="eval_case_test_type", values_callable=_enum_values),
        nullable=False,
    )
    difficulty_snapshot: Mapped[Difficulty] = mapped_column(
        SAEnum(Difficulty, name="eval_case_difficulty", values_callable=_enum_values),
        nullable=False,
    )

    model_response: Mapped[str] = mapped_column(Text, nullable=False)
    # Cosine similarity between model_response and reference_answer_snapshot
    # (see services/embedding_service.py). Null for unanswerable cases,
    # which are scored by a structured judge instead (see
    # services/evaluation_service.py).
    semantic_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    evaluation_reason: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    evaluation_run: Mapped["EvaluationRun"] = relationship(back_populates="results")
    evaluation_case: Mapped["EvaluationCase"] = relationship()
