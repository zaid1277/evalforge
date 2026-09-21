from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.evaluation_case import EvaluationCase, EvaluationStatus
from app.models.project import Project
from app.schemas.export import ExportFormat, ExportStatusFilter
from app.services.export_service import build_export_filename, serialize_csv, serialize_jsonl

router = APIRouter(tags=["export"])

CONTENT_TYPES = {
    "jsonl": "application/x-ndjson",
    "csv": "text/csv",
}


def _get_project_or_404(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


@router.get("/projects/{project_id}/export")
def export_dataset(
    project_id: int,
    export_format: ExportFormat = Query("jsonl", alias="format"),
    status_filter: ExportStatusFilter = Query("approved", alias="status"),
    db: Session = Depends(get_db),
):
    """Export this project's evaluation cases as a downloadable JSONL or
    CSV file. Defaults to only `approved` cases -- generated/rejected
    cases are not considered accepted for use yet. Reads stored
    duplicate_score/grounding_score as-is; never recalculates them and
    never calls Gemini.
    """
    project = _get_project_or_404(db, project_id)

    stmt = select(EvaluationCase).where(EvaluationCase.project_id == project_id)
    if status_filter != "all":
        stmt = stmt.where(EvaluationCase.status == EvaluationStatus(status_filter))
    # Deterministic, stable ordering -- repeated exports of unchanged data
    # produce cases in the same order.
    stmt = stmt.order_by(EvaluationCase.id.asc())

    cases = list(db.scalars(stmt).all())
    if not cases:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No {status_filter} evaluation cases are available to export.",
        )

    content = serialize_jsonl(db, cases) if export_format == "jsonl" else serialize_csv(db, cases)
    filename = build_export_filename(project.name, status_filter, export_format)

    return Response(
        content=content,
        media_type=CONTENT_TYPES[export_format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
