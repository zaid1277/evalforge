from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.chunk import SourceChunk
from app.models.evaluation_case import EvaluationCase
from app.models.evaluation_case_source import EvaluationCaseSource
from app.models.project import Project
from app.schemas.chunk import SourceChunkResponse
from app.schemas.evaluation_case import EvaluationCaseResponse, EvaluationCaseUpdate
from app.services.review_service import CaseValidationError, apply_case_update

router = APIRouter(tags=["evaluation-cases"])


def _get_project_or_404(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


def _get_case_or_404(db: Session, case_id: int) -> EvaluationCase:
    case = db.get(EvaluationCase, case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation case not found."
        )
    return case


@router.get("/projects/{project_id}/cases", response_model=list[EvaluationCaseResponse])
def list_cases(project_id: int, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)
    stmt = (
        select(EvaluationCase)
        .where(EvaluationCase.project_id == project_id)
        .order_by(EvaluationCase.created_at.desc())
    )
    return db.scalars(stmt).all()


@router.get("/cases/{case_id}", response_model=EvaluationCaseResponse)
def get_case(case_id: int, db: Session = Depends(get_db)):
    return _get_case_or_404(db, case_id)


@router.patch("/cases/{case_id}", response_model=EvaluationCaseResponse)
def update_case(case_id: int, payload: EvaluationCaseUpdate, db: Session = Depends(get_db)):
    case = _get_case_or_404(db, case_id)
    try:
        return apply_case_update(db, case, payload)
    except CaseValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/cases/{case_id}/sources", response_model=list[SourceChunkResponse])
def get_case_sources(case_id: int, db: Session = Depends(get_db)):
    """The exact source chunks linked to this case at generation time --
    no new retrieval, no similarity search, nothing substituted."""
    _get_case_or_404(db, case_id)
    stmt = (
        select(SourceChunk)
        .join(EvaluationCaseSource, EvaluationCaseSource.source_chunk_id == SourceChunk.id)
        .where(EvaluationCaseSource.evaluation_case_id == case_id)
        .order_by(SourceChunk.source_document_id, SourceChunk.chunk_index)
    )
    return db.scalars(stmt).all()
