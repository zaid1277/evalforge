from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.evaluation_case import EvaluationCase
    from app.models.evaluation_run import EvaluationRun
    from app.models.source import SourceDocument


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # `server_default=func.now()` lets the database set this value, so it
    # is filled in correctly even if a row is inserted outside the ORM.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # `cascade="all, delete-orphan"` means deleting a Project through the
    # ORM (db.delete(project)) also deletes its SourceDocuments -- no
    # orphaned sources are left behind.
    sources: Mapped[list["SourceDocument"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )

    evaluation_cases: Mapped[list["EvaluationCase"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )

    evaluation_runs: Mapped[list["EvaluationRun"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
