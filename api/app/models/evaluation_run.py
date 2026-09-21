from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.evaluation_result import EvaluationResult
    from app.models.project import Project


class EvaluationRun(Base):
    """One run of an approved dataset against a target model (M9).

    A row here only ever represents a *fully completed* run: see
    services/evaluation_service.py for the atomicity strategy (everything
    is computed in memory first; a run and all its results are written in
    a single transaction only once every case has been answered and
    scored). There is deliberately no `status` column -- a persisted run
    is always complete, so a status that could only ever read "completed"
    would carry no information.
    """

    __tablename__ = "evaluation_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # "mock" or "gemini" -- never a raw API key or other credential.
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)

    total_cases: Mapped[int] = mapped_column(Integer, nullable=False)
    passed_cases: Mapped[int] = mapped_column(Integer, nullable=False)
    failed_cases: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="evaluation_runs")

    results: Mapped[list["EvaluationResult"]] = relationship(
        back_populates="evaluation_run",
        cascade="all, delete-orphan",
        order_by="EvaluationResult.id",
    )
