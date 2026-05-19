from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    # Vault Configuration
    vault_addr: str = Field(default="http://vault:8200")
    vault_root_token: str = Field(default="your_vault_dev_token")

    # Database Configuration
    database_url: str = Field(default="postgresql://user:password@db:5432/dbname")

    # Redis Configuration
    redis_url: str = Field(default="redis://redis:6379/0")

    # MinIO Configuration
    minio_endpoint: str = Field(default="minio:9000")
    minio_root_user: str = Field(default="your_minio_user")
    minio_root_password: str = Field(default="your_minio_password")

    # LLM / Tracing Configuration
    llm_api_key: str = Field(default="your_llm_api_key")
    tracing_key: str = Field(default="your_tracing_api_key")
    tracing_backend_url: str = Field(default="http://jaeger:4317")  # OTLP gRPC endpoint

    # App Secrets
    jwt_secret: str = Field(default="your_jwt_signing_secret")

    # App configuration constraints
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid"
    )

    @property
    def async_database_url(self) -> str:
        """Converts standard postgresql:// URL to asyncpostgresql:// / postgresql+asyncpg://"""
        url = self.database_url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Returns the cached settings instance (Standard 4 Caching)."""
    return Settings()
