from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.source import SourceType


class SourceTextCreate(BaseModel):
    title: str | None = None
    text: str = Field(min_length=1)


class SourceDocumentResponse(BaseModel):
    id: int
    project_id: int
    filename: str
    source_type: SourceType
    raw_text: str
    created_at: datetime
    chunk_count: int

    model_config = ConfigDict(from_attributes=True)


class SourceDocumentSummary(BaseModel):
    """Lighter shape for list endpoints.

    Returning every source's full `raw_text` in a list response could make
    the payload unnecessarily large, so the list endpoint returns metadata
    plus a short preview instead; fetch GET /sources/{id} for full text.
    """

    id: int
    filename: str
    source_type: SourceType
    created_at: datetime
    character_count: int
    preview: str
    chunk_count: int

    model_config = ConfigDict(from_attributes=True)
