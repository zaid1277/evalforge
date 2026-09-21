from fastapi import APIRouter

from app.config import settings
from app.schemas.config import PublicConfigResponse

router = APIRouter(tags=["config"])


@router.get("/config/public", response_model=PublicConfigResponse)
def get_public_config():
    """Safe runtime metadata for the frontend (e.g. the Model Evaluation
    section's "Provider: ... / Model: ..." display). Never returns
    GEMINI_API_KEY or DATABASE_URL -- see schemas/config.py."""
    if settings.USE_MOCK_LLM:
        return PublicConfigResponse(provider="mock", model="mock", mock_mode=True)
    return PublicConfigResponse(
        provider=settings.LLM_PROVIDER, model=settings.GEMINI_MODEL, mock_mode=False
    )
