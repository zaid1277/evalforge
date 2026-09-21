from pydantic import BaseModel, ConfigDict


class SourceChunkResponse(BaseModel):
    id: int
    source_document_id: int
    source_filename: str
    chunk_index: int
    text: str
    word_count: int

    model_config = ConfigDict(from_attributes=True)
