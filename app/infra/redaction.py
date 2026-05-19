import re
import os
import logging
import structlog
from typing import Any, Dict, List, Union

# Compiled regex patterns for all sensitive credentials and identifiers
PATTERNS = [
    # 1. OpenAI API Keys (sk- followed by alphanumeric characters)
    (re.compile(r'sk-[A-Za-z0-9]{20,}'), '[REDACTED_API_KEY]'),
    
    # 2. GitHub Personal Access Tokens (ghp_ followed by alphanumeric characters)
    (re.compile(r'ghp_[A-Za-z0-9]{36}'), '[REDACTED_GH_TOKEN]'),
    
    # 3. Email Addresses (RFC-compliant standard email patterns)
    (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), '[REDACTED_EMAIL]'),
    
    # 4. Credit Card Numbers (standard 16 digit masked combinations)
    (re.compile(r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b'), '[REDACTED_CARD]'),
    
    # 5. AWS Access Key IDs
    (re.compile(r'\bAKIA[0-9A-Z]{16}\b'), '[REDACTED_AWS_KEY]'),
    
    # 6. Slack Webhook URLs
    (re.compile(r'https://hooks\.slack\.com/services/[A-Za-z0-9_]+/[A-Za-z0-9_]+/[A-Za-z0-9_]+'), '[REDACTED_SLACK_WEBHOOK]'),
    
    # 7. Private Keys (RSA, EC, SSH PEM blocks)
    (re.compile(r'-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]+?-----END [A-Z ]+ PRIVATE KEY-----'), '[REDACTED_PRIVATE_KEY]'),
    
    # 8. IP Addresses (strictly checking that octets are between 0-255 to safely ignore version strings like 1.12.0.25)
    (re.compile(r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'), '[REDACTED_IP]'),
    
    # 9. JSON Web Tokens (JWT)
    (re.compile(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b'), '[REDACTED_JWT]'),
    
    # 10. Database Connection Strings (passwords and credentials)
    (re.compile(r'\b\w+:\/\/[^:\s]+:[^@\s]+@\S+\b'), '[REDACTED_CONN_STRING]')
]

def redact(text: str) -> str:
    """
    Applies compiled regex patterns to scrub sensitive data from a raw string.
    """
    if not isinstance(text, str):
        return text
    for pattern, replacement in PATTERNS:
        text = pattern.sub(replacement, text)
    return text

def redact_value(val: Any) -> Any:
    """
    Recursively scans and redacts nested structures (dicts, lists, tuples, strings).
    """
    if isinstance(val, str):
        return redact(val)
    elif isinstance(val, dict):
        return {k: redact_value(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [redact_value(item) for item in val]
    elif isinstance(val, tuple):
        return tuple(redact_value(item) for item in val)
    return val

def structlog_redactor(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    A custom structlog processor that recursively redacts sensitive information
    from all log key-value arguments and event messages.
    """
    for key, value in event_dict.items():
        event_dict[key] = redact_value(value)
    return event_dict

# ----------------------------------------------------------------------
# 🪵 Standard Logging Global Interceptor (Monkeypatching Handler.handle)
# ----------------------------------------------------------------------
original_handle = logging.Handler.handle

def secure_handle(self: logging.Handler, record: logging.LogRecord) -> Any:
    """
    Globally intercepts every standard log record right before it is formatted
    or emitted by any handler, sanitizing the message and format arguments.
    """
    if isinstance(record.msg, str):
        record.msg = redact(record.msg)
    if record.args:
        if isinstance(record.args, dict):
            record.args = {k: redact(v) if isinstance(v, str) else v for k, v in record.args.items()}
        elif isinstance(record.args, tuple):
            record.args = tuple(redact(v) if isinstance(v, str) else v for v in record.args)
    return original_handle(self, record)

# Inject standard logging global handler redaction filter
logging.Handler.handle = secure_handle

# Automatically register our custom processor in the structlog pipeline
try:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.format_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog_redactor,  # Inject redaction layer!
            structlog.processors.JSONRenderer() if os.getenv("JSON_LOGS") else structlog.dev.ConsoleRenderer()
        ]
    )
except RuntimeError:
    # Safe fallback if structlog is already configured (e.g. during imports in test runner)
    pass
