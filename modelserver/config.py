from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class ModelServerSettings(BaseSettings):
    # Paths for model artifacts
    model_path: str = Field(default="/app/models/classifier/model.safetensors")
    model_card_path: str = Field(default="/app/models/classifier/model_card.json")

    # Observability
    tracing_backend_url: str = Field(default="http://jaeger:4317")

    # Developer fallback flag to support mock-mode testing without weights files
    mock_mode: bool = Field(default=True)

    # Bypass heavy HuggingFace downloads for auxiliary models (NER, Summarizer) in offline test environments
    mock_aux_models: bool = Field(default=False)

    # Allow loading from shared .env but ignore extra variables not defined here
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

@lru_cache(maxsize=1)
def get_settings() -> ModelServerSettings:
    """Returns the cached ModelServer settings instance (Standard 4 Caching)."""
    return ModelServerSettings()
