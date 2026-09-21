from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import get_db
from app.models.project import Project
from app.providers.base import ProviderConfigError, ProviderError
from app.providers.factory import get_llm_provider
from app.schemas.generation import GenerationRequest, GenerationResponse
from app.services.generation_service import (
    GenerationFailedError,
    NoChunksAvailableError,
    generate_evaluation_cases,
)

router = APIRouter(tags=["generation"])


def _get_project_or_404(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


@router.post(
    "/projects/{project_id}/generate",
    response_model=GenerationResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_cases(project_id: int, payload: GenerationRequest, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)

    if payload.count > settings.MAX_GENERATION_CASES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"count cannot exceed {settings.MAX_GENERATION_CASES}.",
        )

    try:
        provider = get_llm_provider(settings)
    except ProviderConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc

    try:
        cases = generate_evaluation_cases(db, project_id, provider, payload)
    except NoChunksAvailableError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except GenerationFailedError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc

    return GenerationResponse(
        generated_count=len(cases),
        provider="mock" if settings.USE_MOCK_LLM else settings.LLM_PROVIDER,
        model="mock" if settings.USE_MOCK_LLM else settings.GEMINI_MODEL,
        cases=cases,
    )
