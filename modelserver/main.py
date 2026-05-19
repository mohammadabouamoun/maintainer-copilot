import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request
from fastapi.responses import JSONResponse
import structlog
from opentelemetry import trace

from modelserver.config import ModelServerSettings, get_settings
from modelserver.schemas import ClassifyRequest, ClassifyResponse, NerRequest, NerResponse, SummarizeRequest, SummarizeResponse
from modelserver.classifier import ClassifierModel
from modelserver.ner import NerExtractor
from modelserver.summarizer import Summarizer
from modelserver.exceptions import ModelServerError, ModelArtifactError
from app.infra.tracing import setup_tracing, trace_span_ctx

logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load settings
    settings = get_settings()

    # 1. Setup OpenTelemetry request instrumentation and gRPC Jaeger exporter (Standard 1.5)
    setup_tracing(
        app=app,
        service_name="maintainers-copilot-modelserver",
        otlp_endpoint=settings.tracing_backend_url
    )

    # 2. Initialize and load Classifier Model and NER Extractor singletons
    with trace_span_ctx("lifespan_modelserver_startup") as span:
        classifier = ClassifierModel(settings=settings)
        # load_model acts as the Refuse-to-Boot startup checklist check
        classifier.load_model()
        app.state.classifier = classifier
        span.set_attribute("classifier.status", "loaded")

        # Load NER Extractor
        ner_extractor = NerExtractor()
        ner_extractor.load_pipeline()
        app.state.ner_extractor = ner_extractor
        span.set_attribute("ner_extractor.status", "loaded")

        # Load Summarizer
        summarizer = Summarizer()
        summarizer.load_pipeline()
        app.state.summarizer = summarizer
        span.set_attribute("summarizer.status", "loaded")

    logger.info("ModelServer successfully booted and is ready for inference requests.")
    yield
    logger.info("ModelServer shutting down.")

app = FastAPI(
    title="Maintainer's Copilot ModelServer",
    description="Dedicated microservice for deep learning models (Classifier, NER, Summarization).",
    lifespan=lifespan
)

# Global custom Exception handler for model-specific handled failures
@app.exception_handler(ModelServerError)
async def model_server_error_handler(request: Request, exc: ModelServerError):
    logger.error("ModelServer domain exception occurred", code=exc.code, message=exc.message)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.code,
            "message": exc.message,
            "trace_id": trace.get_current_span().get_span_context().trace_id if trace.get_current_span() else "none"
        }
    )

# Global unhandled exception handler (Standard 7 / needed.md)
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception in ModelServer", error=str(exc))
    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred inside the inference server.",
            "trace_id": trace.get_current_span().get_span_context().trace_id if trace.get_current_span() else "none"
        }
    )

def get_classifier(request: Request) -> ClassifierModel:
    """Dependency injection provider for the loaded ClassifierModel (Standard 2)."""
    classifier = getattr(request.app.state, "classifier", None)
    if classifier is None:
        raise RuntimeError("Classifier has not been initialized.")
    return classifier

@app.post("/classify", response_model=ClassifyResponse)
async def classify(
    payload: ClassifyRequest,
    classifier: ClassifierModel = Depends(get_classifier)
):
    """
    Classifies issue text as a bug, feature, docs, or question.
    Wrapped in an OpenTelemetry trace span with inference performance attributes.
    """
    start_time = time.perf_counter()
    tracer = trace.get_tracer("modelserver")

    with tracer.start_as_current_span("classify_span") as span:
        span.set_attribute("model_name", "classifier")
        span.set_attribute("input_length", len(payload.text))

        # Perform the inference prediction (Standard 1 async thread isolation handled internally)
        result = classifier.predict(payload.text)

        latency_ms = (time.perf_counter() - start_time) * 1000

        span.set_attribute("predicted_label", result["label"])
        span.set_attribute("latency_ms", latency_ms)

        logger.info(
            "Classification completed successfully",
            label=result["label"],
            confidence=result["confidence"],
            latency_ms=latency_ms
        )

        return ClassifyResponse(
            label=result["label"],
            confidence=result["confidence"],
            latency_ms=latency_ms
        )

def get_ner_extractor(request: Request) -> NerExtractor:
    """Dependency injection provider for the loaded NerExtractor (Standard 2)."""
    extractor = getattr(request.app.state, "ner_extractor", None)
    if extractor is None:
        raise RuntimeError("NER Extractor has not been initialized.")
    return extractor

@app.post("/ner", response_model=NerResponse)
async def extract_ner(
    payload: NerRequest,
    extractor: NerExtractor = Depends(get_ner_extractor)
):
    """
    Extracts language and code-shaped entities from issue text.
    Wrapped in an OpenTelemetry trace span with extractor parameters.
    """
    start_time = time.perf_counter()
    tracer = trace.get_tracer("modelserver")

    with tracer.start_as_current_span("ner_span") as span:
        span.set_attribute("model_name", "dslim/bert-base-NER")
        span.set_attribute("input_length", len(payload.text))

        results = extractor.extract(payload.text)

        latency_ms = (time.perf_counter() - start_time) * 1000

        span.set_attribute("entities_count", len(results))
        span.set_attribute("latency_ms", latency_ms)

        logger.info(
            "NER extraction completed successfully",
            entities_count=len(results),
            latency_ms=latency_ms
        )

        return NerResponse(entities=results)

def get_summarizer(request: Request) -> Summarizer:
    """Dependency injection provider for the loaded Summarizer (Standard 2)."""
    summarizer = getattr(request.app.state, "summarizer", None)
    if summarizer is None:
        raise RuntimeError("Summarizer has not been initialized.")
    return summarizer

@app.post("/summarize", response_model=SummarizeResponse)
async def summarize(
    payload: SummarizeRequest,
    summarizer: Summarizer = Depends(get_summarizer)
):
    """
    Summarizes issue threads or descriptions.
    Wrapped in an OpenTelemetry trace span with performance parameters.
    """
    start_time = time.perf_counter()
    tracer = trace.get_tracer("modelserver")

    with tracer.start_as_current_span("summarize_span") as span:
        span.set_attribute("model_name", "sshleifer/distilbart-cnn-12-6")
        span.set_attribute("input_length", len(payload.text))
        span.set_attribute("max_length", payload.max_length)

        summary_text = summarizer.summarize(payload.text, max_length=payload.max_length)

        latency_ms = (time.perf_counter() - start_time) * 1000

        span.set_attribute("summary_length", len(summary_text))
        span.set_attribute("latency_ms", latency_ms)

        logger.info(
            "Summarization completed successfully",
            summary_length=len(summary_text),
            latency_ms=latency_ms
        )

        return SummarizeResponse(summary=summary_text)
