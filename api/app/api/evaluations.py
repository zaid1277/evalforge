from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import get_db
from app.models.evaluation_run import EvaluationRun
from app.models.project import Project
from app.providers.base import ProviderConfigError, ProviderError
from app.providers.factory import get_llm_provider
from app.schemas.evaluation import EvaluationRequest, EvaluationRunResponse, EvaluationRunSummary
from app.schemas.results import EvaluationDashboardResponse
from app.services.evaluation_service import (
    EvaluationFailedError,
    EvaluationLimitExceededError,
    NoApprovedCasesError,
    evaluate_project,
)
from app.services.results_service import build_evaluation_dashboard

router = APIRouter(tags=["evaluations"])


def _get_project_or_404(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


def _get_run_or_404(db: Session, evaluation_id: int) -> EvaluationRun:
    run = db.get(EvaluationRun, evaluation_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation run not found.")
    return run


@router.post(
    "/projects/{project_id}/evaluations",
    response_model=EvaluationRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def run_evaluation(
    project_id: int,
    payload: EvaluationRequest = EvaluationRequest(),
    db: Session = Depends(get_db),
):
    _get_project_or_404(db, project_id)

    try:
        provider = get_llm_provider(settings)
    except ProviderConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc

    provider_name = "mock" if settings.USE_MOCK_LLM else settings.LLM_PROVIDER
    model_name = "mock" if settings.USE_MOCK_LLM else settings.GEMINI_MODEL

    try:
        run = evaluate_project(db, project_id, provider, provider_name, model_name)
    except NoApprovedCasesError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except EvaluationLimitExceededError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except EvaluationFailedError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc

    return run


@router.get("/projects/{project_id}/evaluations", response_model=list[EvaluationRunSummary])
def list_evaluations(project_id: int, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)
    stmt = (
        select(EvaluationRun)
        .where(EvaluationRun.project_id == project_id)
        .order_by(EvaluationRun.created_at.desc())
    )
    return db.scalars(stmt).all()


@router.get("/evaluations/{evaluation_id}", response_model=EvaluationRunResponse)
def get_evaluation(evaluation_id: int, db: Session = Depends(get_db)):
    return _get_run_or_404(db, evaluation_id)


@router.get("/evaluations/{evaluation_id}/dashboard", response_model=EvaluationDashboardResponse)
def get_evaluation_dashboard(evaluation_id: int, db: Session = Depends(get_db)):
    """Derived analytics (M10) over this run's persisted results -- kept
    separate from GET /evaluations/{id} above, which returns the raw run
    + results. Read-only: never reruns, never recalculates
    semantic_similarity, never touches duplicate_score/grounding_score."""
    run = _get_run_or_404(db, evaluation_id)
    return build_evaluation_dashboard(run)
