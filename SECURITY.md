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
