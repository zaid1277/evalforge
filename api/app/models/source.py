import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.chunk import SourceChunk
    from app.models.project import Project


class SourceType(str, enum.Enum):
    """Controlled set of source types. Never taken directly from user
    input -- pasted text is always TEXT, and an upload's type is derived
    from its (validated) file extension. See document_service.py."""

    TEXT = "text"
    TXT = "txt"
    MARKDOWN = "markdown"
    PDF = "pdf"


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # `ondelete="CASCADE"` is a database-level backstop; the ORM-level
    # cascade on Project.sources (see models/project.py) is what actually
    # runs when a project is deleted through the app.
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(
        # `values_callable` makes the stored/compared labels match the
        # lowercase `.value` strings (e.g. "txt") instead of SQLAlchemy's
        # default of using the Python enum member *names* (e.g. "TXT") --
        # keeps what's in the database consistent with what the JSON API
        # shows everywhere else.
        SAEnum(SourceType, name="source_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="sources")

    # Ordered by chunk_index so callers always get chunks in document order
    # without needing to sort them again. `cascade="all, delete-orphan"`
    # means deleting a source also deletes its chunks.
    chunks: Mapped[list["SourceChunk"]] = relationship(
        back_populates="source_document",
        cascade="all, delete-orphan",
        order_by="SourceChunk.chunk_index",
    )

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)
