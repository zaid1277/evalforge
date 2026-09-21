from pydantic import BaseModel


class PublicConfigResponse(BaseModel):
    """Safe-to-expose runtime metadata only -- never GEMINI_API_KEY,
    DATABASE_URL, or any other credential/connection string. Lets the
    frontend show "Provider: Gemini / Model: gemini-3.1-flash-lite" (or
    "Provider: Mock" in USE_MOCK_LLM mode) without duplicating that
    configuration in the frontend's own environment.
    """

    provider: str
    model: str
    mock_mode: bool
