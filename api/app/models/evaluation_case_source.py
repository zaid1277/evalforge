from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.chunk import SourceChunk
    from app.models.evaluation_case import EvaluationCase


class EvaluationCaseSource(Base):
    """Join table recording which source chunks support an evaluation case.

    A surrogate `id` primary key is used (rather than a composite key on
    the two foreign keys) to stay consistent with every other table in
    this project.
    """

    __tablename__ = "evaluation_case_sources"
    __table_args__ = (
        UniqueConstraint(
            "evaluation_case_id", "source_chunk_id", name="uq_eval_case_source_chunk"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    evaluation_case_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # If a chunk is deleted (e.g. its source is removed) this link is
    # cascaded away too, rather than leaving a broken reference. The
    # evaluation case itself is left in place -- see the M4 completion
    # report for why that's the simpler, sufficient behavior for now.
    source_chunk_id: Mapped[int] = mapped_column(
        ForeignKey("source_chunks.id", ondelete="CASCADE"), nullable=False, index=True
    )

    evaluation_case: Mapped["EvaluationCase"] = relationship(back_populates="source_links")
    source_chunk: Mapped["SourceChunk"] = relationship()
