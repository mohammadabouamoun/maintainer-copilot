import functools
import inspect
from contextlib import contextmanager
from typing import Any, Callable, TypeVar, cast, Optional

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider, SpanProcessor, ReadableSpan
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from app.infra.redaction import redact

F = TypeVar("F", bound=Callable[..., Any])

class RedactingSpanProcessor(SpanProcessor):
    """
    OpenTelemetry SpanProcessor that globally filters and redacts sensitive data
    from all span attributes and event/exception attributes before they are exported.
    """
    def __init__(self, span_processor: SpanProcessor):
        self.span_processor = span_processor

    def on_start(self, span: Any, parent_context: Optional[Any] = None) -> None:
        self.span_processor.on_start(span, parent_context)

    def on_end(self, span: ReadableSpan) -> None:
        # 1. Redact direct span attributes (BoundedDict is mutable)
        if hasattr(span, "_attributes") and span._attributes is not None:
            for k, v in list(span._attributes.items()):
                if isinstance(v, str):
                    span._attributes[k] = redact(v)
                elif isinstance(v, (list, tuple)):
                    span._attributes[k] = [redact(item) if isinstance(item, str) else item for item in v]
        
        # 2. Redact event attributes (e.g. exceptions, errors)
        if hasattr(span, "_events") and span._events:
            for event in span._events:
                if hasattr(event, "attributes") and event.attributes:
                    for k, v in list(event.attributes.items()):
                        if isinstance(v, str):
                            event.attributes[k] = redact(v)

        self.span_processor.on_end(span)

    def shutdown(self) -> None:
        self.span_processor.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self.span_processor.force_flush(timeout_millis)


def setup_tracing(app: FastAPI, service_name: str = "maintainers-copilot-api", otlp_endpoint: str = "http://jaeger:4317") -> None:
    """
    Initializes OpenTelemetry Tracer Provider and registers FastAPI request instrumentation.
    Exports spans to Jaeger via OTLP gRPC (Standard 1.5).
    """
    # 1. Define the service resource description
    resource = Resource.create(attributes={
        "service.name": service_name,
        "compose_service": "api"
    })

    # 2. Setup the Tracer Provider
    provider = TracerProvider(resource=resource)
    
    # 3. Configure the OTLP Span Exporter pointing to Jaeger with global redaction
    exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    raw_processor = BatchSpanProcessor(exporter)
    processor = RedactingSpanProcessor(raw_processor)
    provider.add_span_processor(processor)
    
    # 4. Set the global tracer provider
    trace.set_tracer_provider(provider)

    # 5. Automatically instrument all FastAPI incoming HTTP requests
    FastAPIInstrumentor.instrument_app(app)


def get_tracer() -> trace.Tracer:
    """Returns the globally configured tracer instance."""
    return trace.get_tracer("maintainers-copilot")


@contextmanager
def trace_span_ctx(name: str):
    """
    A context manager to wrap code blocks in an OpenTelemetry span.
    Handles exception recording and marks span status as error if it fails (Standard 7).
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as span:
        try:
            yield span
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR, str(e))
            raise


def trace_span(name: str) -> Callable[[F], F]:
    """
    Decorator for both sync and async service layer functions to trace execution as a span.
    Ensures that spans form a correct child-parent hierarchy.
    """
    def decorator(func: F) -> F:
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                with trace_span_ctx(name):
                    return await func(*args, **kwargs)
            return cast(F, async_wrapper)
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                with trace_span_ctx(name):
                    return func(*args, **kwargs)
            return cast(F, sync_wrapper)
    return decorator
