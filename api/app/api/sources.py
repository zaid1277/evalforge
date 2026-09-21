from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import get_db
from app.models.chunk import SourceChunk
from app.models.project import Project
from app.models.source import SourceDocument, SourceType
from app.schemas.chunk import SourceChunkResponse
from app.schemas.source import SourceDocumentResponse, SourceDocumentSummary, SourceTextCreate
from app.services.chunking_service import chunk_text, count_words
from app.services.document_service import (
    DocumentError,
    clean_text,
    decode_text_file,
    extract_pdf_text,
    require_meaningful_text,
    safe_filename,
    source_type_for_filename,
)

router = APIRouter(tags=["sources"])

# Character preview shown in the source list, so the payload stays small
# without needing a second round trip just to see what a source contains.
PREVIEW_LENGTH = 200


def _get_project_or_404(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


def _get_source_or_404(db: Session, source_id: int) -> SourceDocument:
    source = db.get(SourceDocument, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found.")
    return source


def _summarize(source: SourceDocument) -> SourceDocumentSummary:
    return SourceDocumentSummary(
        id=source.id,
        filename=source.filename,
        source_type=source.source_type,
        created_at=source.created_at,
        character_count=len(source.raw_text),
        preview=source.raw_text[:PREVIEW_LENGTH],
        chunk_count=source.chunk_count,
    )


def _create_chunks_for_source(source: SourceDocument) -> None:
    """Generate SourceChunk rows for a source's current raw_text and attach
    them via the `chunks` relationship (persisted on the caller's next
    flush/commit).

    Called right after a source is created (pasted text or file upload --
    both routes below share this one function, so chunk-generation logic
    only lives in one place) and lazily for sources that existed before
    chunking did (see list_source_chunks).
    """
    pieces = chunk_text(
        source.raw_text,
        target_words=settings.CHUNK_TARGET_WORDS,
        max_words=settings.CHUNK_MAX_WORDS,
    )
    for index, piece in enumerate(pieces):
        source.chunks.append(
            SourceChunk(chunk_index=index, text=piece, word_count=count_words(piece))
        )


@router.post(
    "/projects/{project_id}/sources/text",
    response_model=SourceDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_text_source(
    project_id: int, payload: SourceTextCreate, db: Session = Depends(get_db)
):
    _get_project_or_404(db, project_id)

    if len(payload.text.encode("utf-8")) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Text exceeds the {settings.MAX_UPLOAD_SIZE_MB}MB size limit.",
        )

    try:
        require_meaningful_text(payload.text, empty_message="Source text cannot be empty.")
    except DocumentError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    source = SourceDocument(
        project_id=project_id,
        filename=(payload.title or "").strip() or "pasted-text",
        source_type=SourceType.TEXT,
        raw_text=clean_text(payload.text),
    )
    _create_chunks_for_source(source)
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.post(
    "/projects/{project_id}/sources/upload",
    response_model=SourceDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_source(
    project_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)
):
    _get_project_or_404(db, project_id)

    try:
        source_type = source_type_for_filename(file.filename or "")
    except DocumentError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    content = await file.read()
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB}MB upload limit.",
        )

    # Extension is only a hint -- the real validation is whether the file
    # actually decodes/parses as the type it claims to be.
    try:
        if source_type == SourceType.PDF:
            text = extract_pdf_text(content)
        else:
            text = decode_text_file(content)
    except DocumentError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    source = SourceDocument(
        project_id=project_id,
        filename=safe_filename(file.filename),
        source_type=source_type,
        raw_text=text,
    )
    _create_chunks_for_source(source)
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.get("/projects/{project_id}/sources", response_model=list[SourceDocumentSummary])
def list_sources(project_id: int, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)
    stmt = (
        select(SourceDocument)
        .where(SourceDocument.project_id == project_id)
        .order_by(SourceDocument.created_at.desc())
    )
    return [_summarize(source) for source in db.scalars(stmt).all()]


@router.get("/sources/{source_id}", response_model=SourceDocumentResponse)
def get_source(source_id: int, db: Session = Depends(get_db)):
    return _get_source_or_404(db, source_id)


@router.get("/sources/{source_id}/chunks", response_model=list[SourceChunkResponse])
def list_source_chunks(source_id: int, db: Session = Depends(get_db)):
    source = _get_source_or_404(db, source_id)

    # Sources created before M3 existed have no chunks yet. Rather than a
    # separate backfill migration or endpoint, we lazily chunk them the
    # first time anyone asks -- simplest option that keeps every source
    # chunked without extra machinery (see PRD M3 "Existing Sources").
    if not source.chunks:
        _create_chunks_for_source(source)
        db.commit()
        db.refresh(source)

    return source.chunks


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(source_id: int, db: Session = Depends(get_db)):
    source = _get_source_or_404(db, source_id)
    db.delete(source)
    db.commit()
