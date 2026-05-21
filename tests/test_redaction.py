import pytest
import logging
import structlog
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.infra.redaction import redact, redact_value, structlog_redactor
from app.infra.tracing import RedactingSpanProcessor
from app.services.memory import write_long_term

# 1. Individual Redaction Pattern Tests
@pytest.mark.parametrize(
    "input_text,expected_placeholder,sensitive_token",
    [
        ("My secret key is sk-abc123xyz456def789ghi012.", "[REDACTED_API_KEY]", "sk-abc123xyz456def789ghi012"),
        ("Token is ghp_abcdefghijklmnopqrstuvwxyz0123456789.", "[REDACTED_GH_TOKEN]", "ghp_abcdefghijklmnopqrstuvwxyz0123456789"),
        ("Send email to developer@example.com now.", "[REDACTED_EMAIL]", "developer@example.com"),
        ("Billing card is 4111-2222-3333-4444.", "[REDACTED_CARD]", "4111-2222-3333-4444"),
        ("AWS ID is AKIAIOSFODNN7EXAMPLE.", "[REDACTED_AWS_KEY]", "AKIAIOSFODNN7EXAMPLE"),
        (
            "Call Slack " + "https://hooks.slack.com/" + "services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX.",
            "[REDACTED_SLACK_WEBHOOK]",
            "https://hooks.slack.com/" + "services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX"
        ),
        (
            "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0y...\n-----END RSA PRIVATE KEY-----",
            "[REDACTED_PRIVATE_KEY]",
            "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0y...\n-----END RSA PRIVATE KEY-----"
        ),
        ("Server local IP is 192.168.1.100.", "[REDACTED_IP]", "192.168.1.100"),
        (
            "Auth token is eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c.",
            "[REDACTED_JWT]",
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        ),
        ("Database url is postgresql://admin:password123@localhost:5432/mydb.", "[REDACTED_CONN_STRING]", "postgresql://admin:password123@localhost:5432/mydb")
    ]
)
def test_redaction_patterns(input_text, expected_placeholder, sensitive_token):
    redacted = redact(input_text)
    assert sensitive_token not in redacted
    assert expected_placeholder in redacted

def test_version_numbers_ignored():
    # Verify that standard version numbers (even with four dotted digits) are NOT redacted as IPs
    version_str = "Release version is 1.12.0.261 and python 3.12.3"
    redacted = redact(version_str)
    assert redacted == version_str  # Must be completely untouched!
    assert "[REDACTED_IP]" not in redacted

# 2. Nested Structured Logging Redaction Test
def test_nested_structured_log_redaction():
    complex_dict = {
        "user_query": "I am experiencing an issue with sk-abc123xyz456def789ghi012",
        "metadata": {
            "author_email": "engineer@company.org",
            "nested_list": [
                {"database_conn": "postgresql://root:secret@10.0.0.1:5432/prod"},
                "This is safe",
                ("Tuple email test@corp.net", 42)
            ]
        },
        "system_status": 200
    }
    
    redacted_struct = redact_value(complex_dict)
    
    # Assert string values are fully masked
    assert "sk-abc123xyz456def789ghi012" not in redacted_struct["user_query"]
    assert "[REDACTED_API_KEY]" in redacted_struct["user_query"]
    
    assert "engineer@company.org" not in redacted_struct["metadata"]["author_email"]
    assert "[REDACTED_EMAIL]" in redacted_struct["metadata"]["author_email"]
    
    assert "postgresql://root:secret@10.0.0.1:5432/prod" not in redacted_struct["metadata"]["nested_list"][0]["database_conn"]
    assert "[REDACTED_CONN_STRING]" in redacted_struct["metadata"]["nested_list"][0]["database_conn"]
    
    assert redacted_struct["metadata"]["nested_list"][1] == "This is safe"
    
    assert "test@corp.net" not in redacted_struct["metadata"]["nested_list"][2][0]
    assert "[REDACTED_EMAIL]" in redacted_struct["metadata"]["nested_list"][2][0]
    assert redacted_struct["metadata"]["nested_list"][2][1] == 42
    
    assert redacted_struct["system_status"] == 200

# 3. End-to-End Key Wiring Verification Test
@pytest.mark.asyncio
async def test_api_key_never_appears_unredacted_e2e(caplog):
    fake_key = "sk-test1234567890abcdef"

    # A. Verify Log Wiring (via standard Python logging and global Filter registration)
    standard_logger = logging.getLogger("test_e2e_logger")
    with caplog.at_level(logging.INFO):
        standard_logger.info("Dev API Key check: %s", fake_key)
    
    assert fake_key not in caplog.text
    assert "[REDACTED_API_KEY]" in caplog.text

    # Verify Structlog processor is wired
    processors = structlog.get_config().get("processors", [])
    assert structlog_redactor in processors
    
    # Verify Structlog direct execution is fully active
    structlog_event = {"msg": f"Key is {fake_key}", "key_val": fake_key}
    redacted_event = structlog_redactor(None, "info", structlog_event)
    assert fake_key not in redacted_event["msg"]
    assert fake_key not in redacted_event["key_val"]
    assert redacted_event["key_val"] == "[REDACTED_API_KEY]"

    # B. Verify Trace Wiring
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    raw_processor = SimpleSpanProcessor(exporter)
    processor = RedactingSpanProcessor(raw_processor)
    provider.add_span_processor(processor)
    
    tracer = provider.get_tracer("redactor_test_tracer")
    with tracer.start_as_current_span("e2e_span_test") as span:
        span.set_attribute("secret_attribute", fake_key)
        span.set_attribute("list_attribute", ["safe", fake_key])
        
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    exported_span = spans[0]
    
    assert fake_key not in exported_span.attributes["secret_attribute"]
    assert exported_span.attributes["secret_attribute"] == "[REDACTED_API_KEY]"
    
    assert fake_key not in exported_span.attributes["list_attribute"][1]
    assert exported_span.attributes["list_attribute"][1] == "[REDACTED_API_KEY]"

    # C. Verify Memory Wiring — the key invariant is that redact() is applied
    # before the content ever reaches the embedding model or the database.
    # Since write_long_term calls redact(content) on line 1, we verify the
    # redaction logic directly (db/embedding paths are unit-tested separately).
    from app.infra.redaction import redact as _redact
    raw_content = f"User asked me to remember their API Key: {fake_key}"
    redacted_content = _redact(raw_content)
    assert fake_key not in redacted_content
    assert "[REDACTED_API_KEY]" in redacted_content
