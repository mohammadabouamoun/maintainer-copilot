import httpx
import uuid
import traceback
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from opentelemetry import trace
from minio import Minio
from openai import AsyncOpenAI
from fastembed import TextEmbedding

from app.config import get_settings
from app.infra.vault import VaultClient
from app.infra.database import init_db_engine
from app.infra.redis_client import init_redis_client, close_redis_client
from app.infra.tracing import setup_tracing, trace_span_ctx, trace_span
from app.infra.redaction import redact
from app.domain.exceptions import AppError, RequestIDNotFoundError, TracingError, ConfigError
from app.domain.schemas import UserRead, UserCreate, UserUpdate
from app.services.auth import fastapi_users, auth_backend, require_role
import socket
import yaml
from urllib.parse import urlparse

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load global cached settings
    settings = get_settings()
    
    # ── Refuse-to-Boot Checks ──────────────────────────────────────────────────
    # 1. Tracing backend connectivity check
    otlp_endpoint = settings.tracing_backend_url
    if otlp_endpoint:
        parsed = urlparse(otlp_endpoint)
        host = parsed.hostname or "localhost"
        port = parsed.port or 4317
        try:
            with socket.create_connection((host, port), timeout=2.0):
                pass
        except Exception as e:
            raise TracingError(f"Cannot connect to {otlp_endpoint}")

    # 2. Check for 0 or disabled evaluation thresholds
    thresholds_path = "evals/eval_thresholds.yaml"
    if os.path.exists(thresholds_path):
        try:
            with open(thresholds_path, "r") as f:
                thresholds = yaml.safe_load(f)
            
            for metric, value in thresholds.get("classification", {}).items():
                if value == 0 or value is None:
                    raise ConfigError(f"threshold for {metric} is 0 or disabled")
            for metric, value in thresholds.get("rag", {}).items():
                if value == 0 or value is None:
                    raise ConfigError(f"threshold for {metric} is 0 or disabled")
        except ConfigError:
            raise
        except Exception as e:
            raise ConfigError(f"Failed to parse thresholds file: {e}")

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

        # 5. Initialize RAG ML Models and API clients
        logger.info("Loading fastembed TextEmbedding ONNX model (no PyTorch)...")
        retrieval_model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2", cache_dir="./models/fastembed")
        # Cross-encoder reranker requires PyTorch which is excluded from this deployment.
        # RerankerService gracefully falls back to RRF score ordering when model is None.
        reranker_model = None
        
        app.state.retrieval_model = retrieval_model
        app.state.reranker_model = reranker_model
        span.set_attribute("ml_models.status", "loaded")

        # 6. Initialize AsyncOpenAI client
        openai_client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url
        )
        app.state.openai_client = openai_client

        # 7. Initialize MinIO client
        minio_client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_root_user,
            secret_key=settings.minio_root_password,
            secure=False
        )
        # Ensure chunks bucket exists
        bucket_name = "chunks"
        if not minio_client.bucket_exists(bucket_name):
            minio_client.make_bucket(bucket_name)
        app.state.minio_client = minio_client
        span.set_attribute("minio.status", "initialized")

        # 8. Initialize Redis cache
        redis_client = await init_redis_client(settings.redis_url)
        app.state.redis_client = redis_client
        span.set_attribute("redis.status", "initialized")

    yield

    # Clean shutdown of DB engine connection pool and HTTP clients within close span
    with trace_span_ctx("lifespan_shutdown"):
        await app.state.db_engine.dispose()
        await shared_client.aclose()
        await close_redis_client()

app = FastAPI(
    title="Maintainer's Copilot API", 
    description="An AI-powered assistant for open-source maintainers.",
    lifespan=lifespan
)

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
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

# FastAPI-Users Auth & Router Registrations
from app.api.routers.rag import router as rag_router
from app.api.routers.chat import router as chat_router
from app.api.routers.memory import router as memory_router
from app.api.routers.widgets import router as widgets_router

app.include_router(
    rag_router,
    prefix="/rag",
    tags=["rag"]
)

app.include_router(
    chat_router,
    prefix="/chat",
    tags=["chat"]
)

app.include_router(
    memory_router,
    prefix="/memory",
    tags=["memory"]
)

app.include_router(
    widgets_router,
    prefix="/widgets",
    tags=["widgets"]
)

app.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth",
    tags=["auth"]
)

app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"]
)
app.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"]
)

# Protected endpoint for E2E role-check authorization verification
@app.get("/admin/dashboard")
async def admin_dashboard(admin_user=Depends(require_role("admin"))):
    return {
        "status": "success",
        "message": f"Welcome to the admin dashboard, {admin_user.email}!",
        "role": admin_user.role
    }

from fastapi.responses import FileResponse
import os

@app.get("/widget.js")
async def get_widget_js():
    widget_js_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "widget", "public", "widget.js")
    if os.path.exists(widget_js_path):
        return FileResponse(widget_js_path, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="Loader script not found")

