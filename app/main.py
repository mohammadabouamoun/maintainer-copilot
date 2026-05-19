import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config import get_settings
from app.infra.vault import VaultClient
from app.infra.database import init_db_engine
from app.infra.tracing import setup_tracing, trace_span_ctx, trace_span

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load global cached settings
    settings = get_settings()
    
    # Initialize OpenTelemetry exporter and instrument FastAPI (Standard 1.5)
    setup_tracing(
        app=app,
        service_name="maintainers-copilot-api",
        otlp_endpoint=settings.tracing_backend_url
    )

    # Wrap the entire boot lifecycle in a parent initialization trace span
    with trace_span_ctx("lifespan_startup") as span:
        # 1. Create a single shared HTTP client (Standard 3 Singletons)
        shared_client = httpx.AsyncClient(timeout=10.0)
        app.state.http_client = shared_client

        # 2. Initialize Vault client
        vault = VaultClient(settings=settings, client=shared_client)
        app.state.vault = vault

        # 3. Refuse to boot if Vault is unavailable (ping within span)
        await vault.ping()
        span.set_attribute("vault.status", "healthy")

        # 4. Initialize Database Engine singleton
        db_engine = init_db_engine(settings.async_database_url)
        app.state.db_engine = db_engine
        span.set_attribute("database.status", "initialized")

    yield

    # Clean shutdown of DB engine connection pool and HTTP clients within close span
    with trace_span_ctx("lifespan_shutdown"):
        await app.state.db_engine.dispose()
        await shared_client.aclose()

app = FastAPI(
    title="Maintainer's Copilot API", 
    description="An AI-powered assistant for open-source maintainers.",
    lifespan=lifespan
)

@app.get("/health")
@trace_span("health_check")
async def health():
    """Asynchronous health check endpoint (Standard 1 Async) wrapped in an OTel trace span."""
    return {
        "status": "ok",
        "api": "Maintainer's Copilot API is running",
        "tracing": "active"
    }
