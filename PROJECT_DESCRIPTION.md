# Project Description
# Maintainer's Copilot — Project Description

## What It Is

The Maintainer's Copilot is an authenticated, memory-bearing chatbot built for open-source maintainers. Its job is to help a maintainer triage GitHub issues faster: classifying incoming issues by type, extracting key entities from issue text, summarizing long threads, and answering questions by searching over the project's own documentation and resolved-issue history. The whole system is packaged so it can be embedded as a lightweight React widget in any host application — not just run as a standalone page.

---

## What the System Does

### 1. Issue Classification
Three models are trained and compared on the same dataset — closed issues from one chosen open-source repository — labelled as one of `bug`, `feature`, `docs`, or `question`. The three models are:

- A **classical ML baseline** (e.g., TF-IDF + logistic regression / SVM)
- A **fine-tuned small encoder transformer** (e.g., DistilBERT, RoBERTa-base) trained with a real run logger and saved with a model card
- An **LLM zero/few-shot baseline** (prompt-based, same test split)

All three are evaluated on identical stratified splits (test set is strictly more recent than train). A three-way comparison of accuracy, macro-F1, per-class F1, latency, and cost is documented and a single deployment choice is defended.

### 2. NLP Pipelines as Tools
Two additional NLP capabilities are built as FastAPI endpoints that the chatbot can call:

- **NER** — extracts code-shaped entities (function names, error codes, stack traces, package names, version strings) from issue text
- **Summarization** — condenses long issue threads into a short maintainer-readable summary (pre-trained pipeline or LLM-driven)

Both live on a dedicated `modelserver` container, separate from the main API.

### 3. Advanced RAG
A Retrieval-Augmented Generation pipeline answers maintainer questions by searching:

- The project's official documentation
- A held-out slice of resolved issues with maintainer answers (never used in classifier training)

The pipeline goes well beyond a naive baseline:

| Layer | Baseline (beaten) | Implementation |
|---|---|---|
| Chunking | Fixed-size | Semantic / structure-aware strategy |
| Retrieval | Dense-only | Hybrid sparse + dense with tuned weighting |
| Reranking | None | Cross-encoder reranker over top-k |
| Query handling | Raw query | At least one query transformation technique |
| Filtering | None | Metadata filtering over the corpus |

Every choice off the baseline is backed by a number on a 25-question hand-curated golden set.

### 4. Chatbot with Tools and Memory
A single tool-calling LLM (not a multi-agent graph) orchestrates everything. The LLM decides when to call:

- The classifier endpoint
- The NER endpoint
- The summarizer endpoint
- The RAG pipeline
- An explicit `write_memory` tool (memory is never written automatically)

**Short-term memory** lives in Redis with explicit, justified TTLs — conversation state within a session.

**Long-term memory** lives in Postgres with pgvector — at least one of episodic, semantic, or procedural memory, defended in `DECISIONS.md`. Every long-term write produces an audit-log row.

### 5. Embeddable React Widget
The chatbot has two frontend surfaces that share one FastAPI backend:

- **Streamlit app** — internal tool for authenticated maintainers and admins: login, full chat interface, memory inspector, widget configuration panel
- **React widget** — a small standalone bundle (built with Vite) served from MinIO or the API, embeddable in any host app via a single `<script>` tag

The widget supports streamed messages, a collapsible bubble, `postMessage` for iframe resize, and runtime theming (color, position) from a per-widget database config. A loader script at `/widget.js` injects the iframe; the host only pastes one tag with a `data-widget-id`.

**Origin allowlisting** is enforced: `allowed_origins` is stored per widget in Postgres, checked at runtime for CORS and in a `Content-Security-Policy: frame-ancestors` header. Unallowed parents are blocked by the browser — not just rejected by the server.

---

## The Two Technical Tracks

### Deep Learning for NLP
Text processing and representation, fine-tuning transformers, NER/classification/summarization pipelines, ML vs DL vs LLM comparison. The fine-tuned transformer is the core artifact: trained with tracked hyperparameters, saved with a model card (architecture, hyperparameters, data hash, final metrics), and compared rigorously against the other two models.

### LLM Engineering
Advanced RAG (chunking, hybrid retrieval, reranking, query rewriting), RAG and LLM evaluation (RAGAS or a frozen judge), tool-calling chatbots with Redis + pgvector memory, Streamlit + React surfaces, tracing, redacted structured logging, and safe exception handling.

---

## Evaluation-Driven Development

### Golden Sets
- **Classification golden set**: 25 hand-curated issues, run against all three models. Macro-F1, per-class F1, confusion matrix.
- **RAG golden set**: 25 (question, ideal answer, ground-truth chunks) triples. Retrieval metrics (hit@5, MRR@10) and generation metrics (faithfulness, answer relevancy). 5 of the 25 are hand-labeled by the developer; agreement with the judge model is reported.

### CI Gates
Both eval suites run on every push. Thresholds are committed in `eval_thresholds.yaml`. An `eval_report.json` is written each run, stored in MinIO, and diffed against the last green build. **Regression below threshold blocks the merge.** There is no way to ship a regression quietly.

---

## Architectural Non-Negotiables

### Secrets in Vault
Every secret (LLM API keys, JWT signing key, DB password, MinIO credentials, tracing key) resolves from HashiCorp Vault at startup. `.env` holds only the Vault root token and port numbers. `grep -ri 'sk-'` and `grep -ri 'password'` in `app/` return zero matches outside Vault-reading code.

### Blob in MinIO
MinIO stores: fine-tuned model artifacts (or a manifest), all `eval_report.json` runs, training plots, and per-conversation retrieved-chunks snapshots for the last N conversations.

### Layered Codebase
```
app/api/         — HTTP only. Routers touch nothing below FastAPI.
app/services/    — Business logic, transaction boundaries, cache invalidation.
app/repositories/ — SQL only. No HTTP errors, no cache.
app/domain/      — Pydantic domain models (not ORM models).
app/infra/       — Adapters: Vault, MinIO, Redis, LLM providers, model server,
                   tracing backend, redaction layer.
```

### Refuse to Boot
The API refuses to start if: Vault is unreachable, classifier weights are missing, the weights' SHA-256 doesn't match the model card, the tracing backend is misconfigured, or any committed eval threshold is zero or disabled.

### Observability
Every LLM call, tool call, and RAG retrieval is a span. A conversation is a trace tree rooted at the user message. Span attributes include model, token counts, latency, and (redacted) tool inputs/outputs. The trace ID is on every structured log line so logs and traces are joinable.

### Redaction
A redaction layer (in `app/infra/`) runs before any log line, span, or memory write crosses the service boundary. Patterns are defined and defended in `SECURITY.md`. A test explicitly asserts that a fake API key in a user message never appears unredacted in logs, traces, or memory.

### Exception Handling
A domain exception hierarchy (`NotFoundError`, `PermissionDenied`, `ToolFailure`, …) maps to HTTP responses at the API boundary via a single exception handler. Users see a structured error with a code and a request ID — never a stack trace. Tool failures inside the chatbot are caught and recovered gracefully (the LLM reports the failure and continues).

---

## Deployment and Submission

### Compose Stack
All services run with `docker-compose up` from a fresh clone:

| Service | Role |
|---|---|
| `api` | FastAPI — auth, chat, memory, RAG, widget config |
| `chatbot` | Streamlit — admin UI, memory inspector, full chat |
| `widget` | Static server for the React bundle + loader script |
| `modelserver` | FastAPI inference — classifier, NER, summarizer |
| `host` | nginx serving the demo host app |
| `migrate` | Alembic `upgrade head`, then exits |
| `db` | postgres:16 + pgvector |
| `redis` | redis:7 |
| `minio` | minio/minio |
| `vault` | hashicorp/vault (dev mode) |

### CI on Every Push
Lint, type-check, build images, run both eval suites against golden sets, run the redaction test, smoke-test the stack.

### Submission
Public GitHub repo, tagged `v0.1.0-week7`. Submission block includes dataset stats, all three F1 scores, embedding model choice, RAG metrics, memory type, tracing backend, widget bundle size (gzipped), and confirmation of all five required docs (`ARCH.md`, `DECISIONS.md`, `RUNBOOK.md`, `EVALS.md`, `SECURITY.md`).

### Friday Demo (10 minutes)
- Live conversation with cross-conversation recall
- Trace tree walkthrough including one error-path trace
- Widget loading on an allowed host, then blocked on a disallowed host (real browser network tab)
- Live "add a new endpoint or tool" to prove the architecture layers are respected
