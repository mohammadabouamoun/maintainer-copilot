# Security Policy

This document defines and defends the active security **Redaction Layer** compiled inside `app/infra/redaction.py`. The redaction layer runs globally across all logging channels (standard library and `structlog`), OpenTelemetry tracing exports, and database long-term memory operations.

---

## 🔒 Compiled Redaction Patterns & Rationale

We active-mask the following sensitive tokens inside all system text processing boundaries:

### 1. OpenAI API Keys
*   **Regex Pattern:** `sk-[A-Za-z0-9]{20,}`
*   **Replacement:** `[REDACTED_API_KEY]`
*   **Defense & Rationale:** Developers frequently paste raw script snippets or configuration logs into GitHub issues containing their live OpenAI keys. Masking these prevents direct credit theft and billing abuse.

### 2. GitHub Personal Access Tokens
*   **Regex Pattern:** `ghp_[A-Za-z0-9]{36}`
*   **Replacement:** `[REDACTED_GH_TOKEN]`
*   **Defense & Rationale:** Standard prefix-based tokens (`ghp_`) are widely used to authenticate against GitHub repositories. Redacting these stops unauthorized read/write access to third-party or internal repositories.

### 3. Email Addresses
*   **Regex Pattern:** `\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b`
*   **Replacement:** `[REDACTED_EMAIL]`
*   **Defense & Rationale:** Emails represent primary Personally Identifiable Information (PII) under GDPR and CCPA. Redaction protects user privacy within internal tracebacks, memory stores, and database dumps.

### 4. Credit Card Numbers
*   **Regex Pattern:** `\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b`
*   **Replacement:** `[REDACTED_CARD]`
*   **Defense & Rationale:** Compliance with PCI-DSS standards requires that primary account numbers (PAN) never be logged or stored in cleartext.

### 5. AWS Access Keys
*   **Regex Pattern:** `\bAKIA[0-9A-Z]{16}\b`
*   **Replacement:** `[REDACTED_AWS_KEY]`
*   **Defense & Rationale:** AWS programmatic access credentials are high-value targets for server hijacking and massive resource cost farming.

### 6. Slack Webhook URLs
*   **Regex Pattern:** `https://hooks\.slack\.com/services/[A-Za-z0-9_]+/[A-Za-z0-9_]+/[A-Za-z0-9_]+`
*   **Replacement:** `[REDACTED_SLACK_WEBHOOK]`
*   **Defense & Rationale:** Anyone in possession of a Slack webhook can post spam or phishing messages into internal chatrooms. Webhook paths are masked completely.

### 7. Private Keys
*   **Regex Pattern:** `-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]+?-----END [A-Z ]+ PRIVATE KEY-----`
*   **Replacement:** `[REDACTED_PRIVATE_KEY]`
*   **Defense & Rationale:** Private cryptographic keys (SSH, SSL/TLS certificates) represent absolute authority over servers and encrypted traffic. Paste tracebacks containing PEM certificates are instantly blocked.

### 8. IP Addresses
*   **Regex Pattern:** `\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b`
*   **Replacement:** `[REDACTED_IP]`
*   **Defense & Rationale:** Server debug tracebacks and developer issue reports often contain target client IP addresses. Redacting standard IPv4 patterns prevents network mapping.
*   *Octet Boundary Protection:* Using strict standard octet matching (`250-255`, `200-249`, `0-199`) ensures that dotted release/version numbers (e.g. `pandas 1.12.0.261` or `python 3.12.3`) are **never** false-positively redacted, while actual IPs are securely masked.

### 9. JSON Web Tokens (JWT)
*   **Regex Pattern:** `\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b`
*   **Replacement:** `[REDACTED_JWT]`
*   **Defense & Rationale:** JWTs contain active session state, client claims, and user scopes. Masking them prevents session-replay attacks.

### 10. Database Connection Strings
*   **Regex Pattern:** `\b\w+:\/\/[^:\s]+:[^@\s]+@\S+\b`
*   **Replacement:** `[REDACTED_CONN_STRING]`
*   **Defense & Rationale:** Connection URIs frequently contain root usernames, raw cleartext passwords, databases, and database host addresses, exposing database systems to lateral movement.

---

## 🗺️ Where Redaction is Applied in the Stack

Redaction is applied at several key boundaries to prevent sensitive information leakages:
1. **Logging Layer:** Integrated via a custom `structlog` processor and a python standard `logging.Filter` which passes log message strings and dictionary values through `redact()`.
2. **Exception Handling:** The FastAPI global exception handlers for `AppError` and generic `Exception` pass both error messages and raw stack tracebooks through `redact()` before logging.
3. **OpenTelemetry Span Processor:** Registered as `RedactingSpanProcessor`, it intercepts spans before exporting them to Jaeger, sanitizing span attributes and exception events.
4. **Long-Term Memory Storage:** The `write_long_term` service sanitizes all memory content string payloads before generating vector embeddings and saving them to the PostgreSQL database.

---

## 🕵️ Trace: A User Pastes a GitHub Token Into the Chat

If a user pastes a GitHub token (`ghp_...`) into the chat interface, let's trace every place it could appear **with** and **without** redaction:

### 1. Places It Appears WITHOUT Redaction (Cleartext)
*   **Network Request Payload:** The HTTP POST request body sent from the React widget browser bundle to `/chat/message` (intercepted by reverse proxies / TLS termination endpoints).
*   **FastAPI In-Memory State:** The raw string variable within the python memory space inside the FastAPI uvicorn worker thread.
*   **Redis Short-Term Cache:** Stored inside the conversation history list (`conversations:{conversation_id}`) in cleartext to ensure the LLM receives the exact, unmodified query.
*   **Outbound LLM Request:** Sent in cleartext via HTTPS to the external LLM provider (e.g. OpenAI/Groq API) for inference.

### 2. Places It is GUARANTEED to be REDACTED
*   **Stdout/Stderr Console Logs:** Any logger statement recording user input or session logs is scrubbed to output `[REDACTED_GH_TOKEN]`.
*   **OpenTelemetry traces:** Spans displayed in Jaeger dashboard will have attributes like `user_message` redacted.
*   **System Exceptions / Tracebacks:** If a database error or network timeout occurs, any logged traceback containing the message string is fully sanitized.
*   **Long-Term Memories Vector DB:** If the LLM invokes the `write_memory` tool to store a preference, it is redacted before database write and embedding generation.
