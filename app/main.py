import httpx
import uuid
import traceback
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from opentelemetry import trace

from app.config import get_settings
from app.infra.vault import VaultClient
from app.infra.database import init_db_engine
from app.infra.tracing import setup_tracing, trace_span_ctx, trace_span
from app.infra.redaction import redact
from app.domain.exceptions import AppError, RequestIDNotFoundError

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

logger = structlog.get_logger()

# 1. Request correlation middleware
class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Allow testing dynamic missing request IDs intentionally
        if request.headers.get("X-Test-Fail-Request-ID"):
            raise RequestIDNotFoundError()

        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())
            
        if not request_id:
            raise RequestIDNotFoundError()

        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

app.add_middleware(RequestIdMiddleware)

# Helper to resolve active OTel Trace ID
def get_active_trace_id() -> str:
    span = trace.get_current_span()
    span_context = span.get_span_context() if span else None
    if span_context and span_context.is_valid:
        return trace.format_trace_id(span_context.trace_id)
    return "unknown"

# 2. Global exception handler for AppError domain subclassing
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    request_id = getattr(request.state, "request_id", "unknown")
    trace_id = get_active_trace_id()

    # Defense-in-depth: explicitly redact the message before passing to logger
    redacted_message = redact(exc.message)

    logger.error(
        "Application domain exception occurred",
        error_code=exc.code,
        error_message=redacted_message,
        request_id=request_id,
        trace_id=trace_id
    )

    return JSONResponse(
        status_code=exc.http_status,
        headers={"X-Request-ID": request_id},
        content={
            "error": exc.code,
            "message": redacted_message,
            "request_id": request_id
        }
    )

# 3. Global catch-all handler for unhandled Exceptions (e.g. ZeroDivisionError)
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    trace_id = get_active_trace_id()

    # Defense-in-depth: redact exception message and full traceback details
    exc_str = redact(str(exc))
    tb_str = redact(traceback.format_exc())

    logger.error(
        "Unhandled system exception occurred",
        error_message=exc_str,
        traceback=tb_str,
        request_id=request_id,
        trace_id=trace_id
    )

    # Client shielding: NEVER expose message or stack traces to clients
    return JSONResponse(
        status_code=500,
        headers={"X-Request-ID": request_id},
        content={
            "error": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred. Please contact support.",
            "request_id": request_id
        }
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

# Dynamic endpoints explicitly for exception and E2E error handling verification
@app.get("/test-error/domain")
async def test_domain_error(error_type: str):
    from app.domain import exceptions
    if error_type == "not_found":
        raise exceptions.NotFoundError("Missing resource matching id 999.")
    elif error_type == "permission":
        raise exceptions.PermissionDenied("Admin privileges required.")
    elif error_type == "too_many_requests":
        raise exceptions.TooManyRequestsError("Too many API requests sent.")
    elif error_type == "model_server":
        raise exceptions.ModelServerError("ModelServer connection timed out.")
    return {"status": "ok"}

@app.get("/test-error/unhandled")
async def test_unhandled_error():
    # Intentionally trigger unhandled division by zero to test shielding
    return 1 / 0
