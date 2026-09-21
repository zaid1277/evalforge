from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.source import SourceDocument


class SourceChunk(Base):
    __tablename__ = "source_chunks"
    __table_args__ = (
        # A source can't have the same chunk_index twice.
        UniqueConstraint("source_document_id", "chunk_index", name="uq_source_chunk_index"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    source_document_id: Mapped[int] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Zero-based position of this chunk within its source, preserving the
    # original document order (0, 1, 2, ...).
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    text: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    source_document: Mapped["SourceDocument"] = relationship(back_populates="chunks")

    @property
    def source_filename(self) -> str:
        return self.source_document.filename
