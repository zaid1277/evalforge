"""
Tiny provider-selection function -- not a dependency-injection framework,
just an if/else that reads configuration and returns the right provider.
"""

from app.config import Settings
from app.providers.base import LLMProvider, ProviderConfigError
from app.providers.gemini_provider import GeminiProvider
from app.providers.mock_provider import MockProvider


def get_llm_provider(settings: Settings) -> LLMProvider:
    if settings.USE_MOCK_LLM:
        return MockProvider()

    if settings.LLM_PROVIDER == "gemini":
        if not settings.GEMINI_API_KEY:
            raise ProviderConfigError("Gemini API key is not configured.")
        return GeminiProvider(api_key=settings.GEMINI_API_KEY, model=settings.GEMINI_MODEL)

    raise ProviderConfigError(f"Unknown LLM_PROVIDER '{settings.LLM_PROVIDER}'.")
