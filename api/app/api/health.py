from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health_check():
    """Simple liveness check used by developers and deployment tooling."""
    return {"status": "ok"}
