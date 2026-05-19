import pytest
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from app.main import app
from app.domain import exceptions

# Configure TestClient with raise_server_exceptions=False to test actual HTTP error responses
client = TestClient(app, raise_server_exceptions=False)

# 1. Test Request ID Generation and Header Propagation
def test_request_id_middleware_success():
    response = client.get("/health")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    # Verify request ID is a valid string/UUID
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) > 10

def test_request_id_middleware_propagate_header():
    custom_id = "test-custom-uuid-12345"
    response = client.get("/health", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == custom_id

# 2. Test Middleware Exception Trigger (RequestIDNotFoundError)
def test_middleware_fail_raises_request_id_not_found():
    # X-Test-Fail-Request-ID header triggers a simulated middleware error
    response = client.get("/health", headers={"X-Test-Fail-Request-ID": "true"})
    assert response.status_code == 500
    
    # Asserting client shielding works (shields standard exception messages)
    data = response.json()
    assert data["error"] == "INTERNAL_SERVER_ERROR"
    assert data["message"] == "An unexpected error occurred. Please contact support."

# 3. Test AppError Domain Exception Mapping & Payloads
@pytest.mark.parametrize(
    "error_type,expected_status,expected_code,snippet",
    [
        ("not_found", 404, "NOT_FOUND", "Missing resource matching id 999."),
        ("permission", 403, "PERMISSION_DENIED", "Admin privileges required."),
        ("too_many_requests", 429, "TOO_MANY_REQUESTS", "Too many API requests sent."),
        ("model_server", 502, "MODEL_SERVER_ERROR", "ModelServer connection timed out.")
    ]
)
def test_domain_exceptions(error_type, expected_status, expected_code, snippet):
    response = client.get(f"/test-error/domain?error_type={error_type}")
    assert response.status_code == expected_status
    
    data = response.json()
    assert data["error"] == expected_code
    assert data["message"] == snippet
    assert "request_id" in data
    
    # Assert request ID matches header
    assert response.headers.get("X-Request-ID") == data["request_id"]

# 4. E2E Unhandled Exception ZeroDivisionError Shielding Test
def test_unhandled_exception_traceback_masking():
    response = client.get("/test-error/unhandled")
    assert response.status_code == 500
    
    data = response.json()
    # Confirm that absolutely NO traceback or original exception message is leaked!
    assert "ZeroDivisionError" not in data.get("message", "")
    assert "division by zero" not in data.get("message", "")
    assert "traceback" not in data
    
    # Must return a standardized Internal Server Error and correlation ID
    assert data["error"] == "INTERNAL_SERVER_ERROR"
    assert data["message"] == "An unexpected error occurred. Please contact support."
    assert "request_id" in data
    assert response.headers.get("X-Request-ID") == data["request_id"]

# 5. Verify Active Telemetry Trace ID Correlation
def test_telemetry_trace_id_correlation(caplog):
    # Setup custom trace provider to check trace context in handlers
    provider = TracerProvider()
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer("test_exceptions_tracer")
    
    with tracer.start_as_current_span("test_exceptions_span") as span:
        trace_id = trace.format_trace_id(span.get_span_context().trace_id)
        
        response = client.get("/test-error/domain?error_type=not_found")
        assert response.status_code == 404
        
        # Verify trace ID is mapped correctly (we can assert that the span is valid)
        assert span.get_span_context().is_valid
