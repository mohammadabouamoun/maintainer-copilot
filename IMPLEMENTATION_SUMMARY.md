# Maintainer's Copilot — Implementation Progress & Current State

This document provides a highly detailed summary of the architectural layout, implemented components, configuration state, and next steps for the **Maintainer's Copilot** repository. This file serves as the handoff document for continuing the development session.

**Last Updated:** Phase 4.5 complete — Memory layer integrated, PyTorch removed.

---

## 1. Project Overview & Architectural Foundations

The **Maintainer's Copilot** is a production-grade, secure, and memory-bearing chatbot framework designed to help open-source maintainers triage GitHub issues. It provides automated sequence classification, Named Entity Recognition (NER), long-thread summarization, and Retrieval-Augmented Generation (RAG) over project docs and historical resolved issues. It is built to support a standalone Streamlit admin panel as well as a lightweight, origin-allowlisted, and themeable React chatbot widget embedded via a simple `<script>` tag.

---

## 2. Directory Layout & Repository Structure

```
maintainer-copilot/
├── app/                            # Main FastAPI backend codebase
│   ├── api/
│   │   └── routers/
│   │       ├── rag.py              # POST /rag/query endpoint
│   │       └── chat.py             # POST /chat/message, GET /chat/conversations/{id}
│   ├── domain/
│   │   ├── exceptions.py           # Core custom domain exceptions
│   │   └── schemas.py              # Shared Pydantic request/response schemas
│   ├── infra/
│   │   ├── database.py             # SQLAlchemy async engine & session provider
│   │   ├── redaction.py            # 10-pattern PII/API key scrubbing layer
│   │   ├── tracing.py              # OTel + Jaeger setup, RedactingSpanProcessor
│   │   └── vault.py                # HashiCorp Vault KV secret provider
│   ├── repositories/
│   │   └── models.py               # SQLAlchemy declarative models (User, Conversation, Message, LongTermMemory, AuditLog, Widget)
│   ├── services/
│   │   ├── auth.py                 # fastapi-users JWT authentication service
│   │   ├── chatbot.py              # Tool-calling LLM loop with streaming & failure shields
│   │   ├── memory.py               # Long-term memory write & recall stubs
│   │   ├── rag_service.py          # Full RAG orchestrator (transform→retrieve→rerank→generate→snapshot)
│   │   ├── reranker.py             # Cross-encoder reranking service
│   │   ├── retrieval.py            # Hybrid dense+sparse retrieval with RRF fusion
│   │   └── transform.py            # LLM-based query rewriting service
│   ├── config.py                   # Global Settings via Pydantic BaseSettings
│   └── main.py                     # FastAPI lifespan, middleware, routers
├── chatbot/                        # Streamlit admin application (skeleton)
├── data/                           # Local data directory (git-ignored)
│   ├── raw/issues.jsonl            # ~3,600 fetched FastAPI GitHub issues
│   ├── splits/
│   │   ├── train.jsonl             # 2,627 training samples
│   │   ├── val.jsonl               # 464 validation samples
│   │   └── test.jsonl              # 545 temporally-constrained test samples
│   ├── classical_metrics.json      # TF-IDF + LogReg baseline metrics
│   └── golden_classification.jsonl # 25-example labelled golden dataset
├── evals/
│   ├── run_rag_eval.py             # End-to-end RAG evaluator (25 Q&A pairs)
│   ├── eval_report_rag.json        # RAG evaluation output report
│   ├── golden_results.json         # Live microservice golden-set results
│   ├── llm_baseline_results.json   # LLM zero-shot baseline metrics
│   └── eval_thresholds.yaml        # CI metric regression limits
├── migrations/
│   └── versions/c782351e96b9_baseline.py  # Alembic SQL baseline migration
├── models/
│   ├── classifier/
│   │   ├── model.safetensors       # Fine-tuned DistilBERT weights
│   │   ├── config.json
│   │   ├── tokenizer.json
│   │   └── model_card.json         # SHA-256 checksum + performance metrics
│   └── classical/model.pkl         # TF-IDF + LogisticRegression pipeline
├── modelserver/
│   ├── config.py                   # ModelServer settings
│   ├── schemas.py                  # ClassifyRequest/Response, NerRequest/Response, SummarizeRequest/Response
│   ├── exceptions.py               # ModelServerError, ModelArtifactError
│   ├── classifier.py               # ONNX/SafeTensor classifier loader
│   ├── ner.py                      # HuggingFace NER + regex fallback
│   ├── summarizer.py               # DistilBART summarizer + mock fallback
│   ├── train_classical.py          # TF-IDF + LogReg trainer script
│   └── main.py                     # Lifespan boot, /classify, /ner, /summarize endpoints
├── prompts/
│   ├── query_rewrite.txt           # LLM query rewriting instruction template
│   ├── rag_answer.txt              # Anti-hallucination RAG grounding prompt
│   └── system.txt                  # Chatbot identity & tool guidance prompt
├── scripts/
│   ├── build_splits.py             # Stratified temporal data splitter
│   ├── fetch_issues.py             # GitHub Search API issue downloader
│   ├── preprocess_corpus.py        # Pandas RST docs + issues → chunks
│   ├── compare_embeddings.py       # Embedding model benchmarking
│   ├── ingest_corpus.py            # Embeds & seeds PostgreSQL corpus_chunks table
│   ├── generate_golden_set.py      # RAG golden Q&A pair generator
│   ├── eval_golden_set.py          # Golden set microservice evaluator
│   ├── eval_llm_baseline.py        # LLM zero-shot evaluator
│   └── vault_init.sh               # Vault KV bootloader & secret seeder
├── scratch/                        # Sandbox/debug scripts
├── tests/
│   ├── test_auth.py                # Auth & RBAC integration tests
│   ├── test_chatbot.py             # Chatbot streaming + tool-call E2E tests
│   ├── test_exceptions.py          # Exception handler & middleware tests
│   ├── test_onnx_classifier.py     # Classifier model inference tests
│   ├── test_rag_pipeline.py        # RAG pipeline + MinIO snapshot E2E tests
│   └── test_redaction.py           # Redaction layer coverage tests
├── colab_training/
│   ├── INSTRUCTIONS.md
│   └── notebook_cells.txt          # Copy-pasteable Colab fine-tuning cells
├── widget/                         # React Vite widget (skeleton)
├── .env                            # Local dev secrets (git-ignored)
├── .env.example                    # Safe example env template
├── .gitignore                      # Excludes data/, models/, .env, __pycache__
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── ARCH.md
├── DECISIONS.md
├── SECURITY.md
└── STEP_BY_STEP_TASKS.md
```

---

## 3. Configured Services (Docker Compose Stack)

| Service | Image / Port | Role |
|---|---|---|
| `api` | `Dockerfile` (8000) | Main FastAPI backend. Depends on `db` healthy + `vault` healthy + `migrate` exit 0. |
| `chatbot` | `Dockerfile` (8501) | Streamlit dashboard. Depends on `api`. |
| `modelserver` | `Dockerfile` (8001) | Dedicated ML inference server (`/classify`, `/ner`, `/summarize`). |
| `widget` | `node:20-alpine` (3000) | Vite dev server for the React embed widget. |
| `host` | `nginx:alpine` (9000) | Serves the mock consumer page embedding the widget. |
| `migrate` | `Dockerfile` | Runs `alembic upgrade head` once and exits. |
| `db` | `pgvector/pgvector:pg16` (5432) | PostgreSQL 16 with pgvector extension. |
| `redis` | `redis:7-alpine` (6379) | Session history cache (short-term memory TTL). |
| `minio` | `minio/minio` (9002/9001) | S3-compatible object store for corpus snapshots & RAG audit chunks. |
| `vault` | `hashicorp/vault` (8200) | Developer Vault KV for API keys, DB credentials, JWT secrets. |
| `vault-init` | `hashicorp/vault` | Seeds KV secrets on first boot via `vault_init.sh`. |
| `jaeger` | `jaegertracing/all-in-one` (16686/4317) | OTel collector & distributed trace dashboard. |

---

## 4. Phase 1 & 2: Infrastructure, Dataset & ML Models

### 4.1 Secret Management & Refuse-to-Boot Pattern (`app/main.py`, `app/infra/vault.py`)
- **`VaultClient`** (`app/infra/vault.py`): `async` Vault HTTP client with `ping()` health check and `get_secret(path)` retrieval.
- **FastAPI Lifespan (`app/main.py`):** On startup:
  1. Pings Vault — raises `VaultUnavailableError` and halts boot if unreachable.
  2. Creates the SQLAlchemy async engine.
  3. Sets up OTel tracer with Jaeger gRPC exporter.
  4. Mounts all routers.
- **`scripts/vault_init.sh`:** Seeds all secrets (JWT, DB, MinIO, LLM, OTel) into Vault KV on container first-boot.

### 4.2 Database Schema & Alembic Migration
- **`app/repositories/models.py`:** Declarative SQLAlchemy models:
  - `User` — email, hashed password, role (`admin`/`user`), `is_active`, `is_verified`.
  - `Conversation` / `Message` — multi-turn history (roles: `system`, `user`, `assistant`).
  - `LongTermMemory` — `Vector(768)` column for semantic recall, `memory_type` (`episodic`, `semantic`, `procedural`).
  - `AuditLog` — security audit trail (`actor_id`, `action`, `target`, `timestamp`).
  - `Widget` — theme JSONB, `allowed_origins[]`, `enabled_tools[]`, greeting.
- **`migrations/versions/c782351e96b9_baseline.py`:** Autogenerated Alembic migration creating all tables and running `CREATE EXTENSION IF NOT EXISTS vector;`.

### 4.3 OpenTelemetry Tracing (`app/infra/tracing.py`)
- OTel `BatchSpanExporter` → Jaeger gRPC on port `4317`.
- `FastAPIInstrumentor.instrument_app(app)` auto-instruments all HTTP requests.
- `trace_span_ctx(name)` context manager and `@trace_span(name)` decorator for service-level child spans.
- **`RedactingSpanProcessor`:** Custom OTel processor that intercepts spans before export and scrubs all attributes and event properties through the redaction layer.

### 4.4 Enterprise Redaction Layer (`app/infra/redaction.py`)
- 10 compiled regex patterns covering: OpenAI/Groq/GitHub/AWS API keys, JWTs, private PEM keys, email addresses, credit card numbers, Slack webhooks, DB connection strings, and IP addresses.
- **Global log interception:** Overrides `logging.Handler.handle` and `structlog` pipeline globally — every log line in the entire system (including third-party libraries) is scrubbed in-place.
- **Memory safety gate:** `write_long_term()` in `app/services/memory.py` runs redaction before any DB write.
- **Verified** by `tests/test_redaction.py` (13 test cases, 100% passing).

### 4.5 Authentication & RBAC (`app/services/auth.py`)
- Built on `fastapi-users` with `SQLAlchemy` async adapter.
- JWT bearer token strategy with configurable secret from Vault.
- `current_active_user` dependency used across all protected endpoints.
- Role-based access: `user` and `admin` roles enforced by custom middleware checks.
- **Verified** by `tests/test_auth.py`.

### 4.6 Dataset & ML Training
- **Data Acquisition (`scripts/fetch_issues.py`):** Downloaded ~3,600 closed issues from `fastapi/fastapi` via GitHub Search API, balanced across 4 label classes.
- **Temporal Splits (`scripts/build_splits.py`):** Stratified 70/15/15 split with strict temporal constraint — `min(test.created_at) > max(train.created_at)`.
- **Fine-tuned DistilBERT** trained on Colab (cells in `colab_training/notebook_cells.txt`): `title + " [SEP] " + body[:512]` input format, SHA-256 weight checksum in `model_card.json`.
- **Classical baseline** (`modelserver/train_classical.py`): TF-IDF (unigrams+bigrams, `max_features=10000`) + `LogisticRegression(C=1.0, max_iter=1000)`.

**Three-way model comparison (documented in `DECISIONS.md`):**

| Model | Accuracy | Macro-F1 | Latency | Cost/1k |
|---|---|---|---|---|
| Classical ML (TF-IDF + LogReg) | 69.72% | 54.17% | **0.27 ms** | $0.00 |
| Fine-tuned DistilBERT | 71.19% | 55.68% | 169.64 ms | $0.00 |
| LLM Zero-Shot | **76.33%** | **73.93%** | 934.84 ms | $0.03 |

**Decision:** Fine-tuned DistilBERT selected for production — best balance of accuracy, zero cost, data privacy, and sub-200 ms latency.

### 4.7 ModelServer (`modelserver/main.py`)
- Dedicated FastAPI microservice on port `8001`.
- **Lifespan refuse-to-boot:** Validates `model.safetensors` SHA-256 against `model_card.json` on startup.
- **Resilient HuggingFace fallbacks:** NER and Summarizer pipelines gracefully degrade to regex/mock modes if HF Hub is unreachable (guarantees < 1s startup in CI).
- Three endpoints:
  - `POST /classify` → `{label, confidence, latency_ms}`
  - `POST /ner` → `{entities: [{text, label, start, end}]}`
  - `POST /summarize` → `{summary}`
- All endpoints wrapped in OTel child spans with latency attributes.
- **Golden Set Evaluation:** 80.0% accuracy, 63.89% Macro-F1, 174.96 ms avg latency on 25 hand-labelled examples.

---

## 5. Phase 3: Advanced RAG Pipeline

### 5.1 Corpus Preprocessing (`scripts/preprocess_corpus.py`)
- Cloned `pandas-dev/pandas`, parsed `.rst` docs segmented at primary headers → **1,740 documentation chunks**.
- Filtered held-out issues (IDs not in train/val/test splits) → **500 issue knowledge-base chunks**. Zero data leakage.

### 5.2 Embedding Model Selection (`scripts/compare_embeddings.py`, `scripts/ingest_corpus.py`)
- Benchmarked multiple models; selected **`sentence-transformers/all-MiniLM-L6-v2`** (384-dim): Hit@5 = `1.0`, MRR@10 = `1.0`, avg latency `< 39 ms` on CPU.
- `ingest_corpus.py` seeds the `corpus_chunks` PostgreSQL table with embeddings.
- MinIO corpus snapshot (`corpus_snapshot.json`) uploaded for reproducible deployments.

### 5.3 Hybrid Retrieval Service (`app/services/retrieval.py`)
- **Dense search:** pgvector cosine similarity over 384-dim embeddings.
- **Sparse search:** Postgres `to_tsquery` with logical `OR` (`|`) keyword expansion — resolves the strict `AND` bottleneck that returned 0 results on partial queries.
- **RRF Fusion:** Reciprocal Rank Fusion (`k=60`) merges dense and sparse rankings into a unified candidate list.

### 5.4 Cross-Encoder Neural Reranking (`app/services/reranker.py`)
- Uses `cross-encoder/ms-marco-MiniLM-L-6-v2` loaded at startup.
- Candidate depth expanded to **60** to maximize reranking precision.
- Returns top-N by direct query-document attention score.

### 5.5 LLM Query Rewriting (`app/services/transform.py`)
- `QueryTransformService.rewrite(query)` calls the LLM with `prompts/query_rewrite.txt`.
- Rewrites natural-language questions into search-optimized technical keyword strings (method names, parameter signatures, etc.) before retrieval.

### 5.6 RAG Evaluation (`evals/run_rag_eval.py`)
- 25 Q&A pairs: 20 LLM-synthesized + 5 hand-labelled edge cases.
- LLM-as-a-Judge scores Faithfulness and Answer Relevancy in strict JSON.

| Metric | Score | Threshold | Result |
|---|---|---|---|
| Hit@5 (Recall) | **0.75** | 0.70 | ✅ PASS |
| MRR@10 | **0.6542** | — | ✅ |
| Faithfulness | **0.9440** | 0.75 | ✅ PASS |
| Answer Relevancy | **0.6500** | 0.60 | ✅ PASS |

### 5.7 Exception Handling & Correlation Middleware (`app/main.py`, `app/domain/exceptions.py`)
- **Domain exception hierarchy:** `NotFoundError` (404), `PermissionDenied` (403), `TooManyRequestsError` (429), `ToolFailure` (502), `VaultUnavailableError` (503), `ModelServerError` (502), `RequestIDNotFoundError` (500).
- **`RequestIdMiddleware`:** Stamps every request/response with `X-Request-ID` (UUIDv4) stored in ASGI context.
- **Generic handler:** Catches all unhandled exceptions (e.g. `ZeroDivisionError`), returns structured `500 INTERNAL_SERVER_ERROR` JSON with correlation ID — no internal traceback leak.
- Trace ID and request ID are co-emitted in every log and error response for full E2E observability.
- **Verified** by `tests/test_exceptions.py` (9 test cases).

---

## 6. Phase 4.1 & 4.2: Authentication, RAG Endpoint & MinIO Auditing

### 6.1 Lifespan Model Singletons (`app/main.py`)
On application startup, the lifespan now also initializes:
- `SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")` → `app.state.retrieval_model`
- `CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")` → `app.state.reranker_model`
- `AsyncOpenAI(api_key=..., base_url=...)` → `app.state.openai_client`
- `Minio(endpoint=..., access_key=..., secret_key=...)` → `app.state.minio_client`
- Ensures MinIO bucket `chunks` exists (creates it if missing).

All models are loaded **once** at boot — zero cold-start penalty per request.

### 6.2 RAG Service (`app/services/rag_service.py`)
`RAGService.query(question, conversation_id, metadata_filter)` orchestrates:

| Step | OTel Span | Description |
|---|---|---|
| 1 | `query_transform` | Rewrites the question via `QueryTransformService` |
| 2 | `hybrid_retrieve` | Fetches top-60 candidates via `RetrievalService` (dense+sparse+RRF) |
| 3 | `rerank` | Sorts candidates via `RerankerService` (cross-encoder), keeps top-5 |
| 4 | `generate_answer` | Calls Groq `llama-3.1-8b-instant` with `prompts/rag_answer.txt` grounding prompt |
| 5 | `save_snapshot` | Uploads top-5 chunk JSON to MinIO at `chunks/{conversation_id}/{timestamp}.json` |

All spans are children of the parent `rag_query` span, providing full Jaeger trace hierarchy.

### 6.3 RAG Grounding Prompt (`prompts/rag_answer.txt`)
Strict anti-hallucination instruction — LLM is explicitly prohibited from using any knowledge outside the provided context chunks. Forces answers to cite only retrieved material.

### 6.4 RAG API Router (`app/api/routers/rag.py`)
- `POST /rag/query` — JWT-protected (`current_active_user`).
- Returns `{answer, chunks[], trace_id}`.
- **Verified** by `tests/test_rag_pipeline.py`: registers user → authenticates → sends query → validates MinIO snapshot upload.

---

## 7. Phase 4.3: Chatbot Service — Tool-Calling LLM

### 7.1 Configuration Update (`app/config.py`)
Added `modelserver_url: str = Field(default="http://modelserver:8001")` — cleanly switchable between Docker-internal hostname and `localhost:8001` for local test runs.

### 7.2 Chatbot Identity Prompt (`prompts/system.txt`)
Defines the assistant's persona ("Maintainer's Copilot"), communication style (professional, concise, markdown), available tools, and the rule that `write_memory` must only be invoked when the user explicitly requests a fact to be remembered.

### 7.3 Chatbot Orchestrator (`app/services/chatbot.py`)
`ChatbotService.chat(conversation_id, user_message, user_id) -> AsyncIterator[str]` implements the full loop:

```
1. _ensure_conversation()       → Creates Conversation row if new
2. _load_history()              → Fetches ordered Messages from Postgres
3. recall_relevant()            → Retrieves relevant long-term memories (injected into system prompt)
4. Build messages[]             → [SystemPrompt + memories] + history + [UserMessage]
5. LLM call with tools          → tool_choice="auto", temperature=0.0
6. Tool call loop (while True):
   ├── If no tool_calls → break
   ├── Dispatch to tool handler (try/except → ToolFailure JSON on any error)
   ├── Append tool call + result to messages[]
   └── Re-call LLM with updated messages
7. _save_message(user)          → Persist user message to Postgres
8. Streaming LLM call           → stream=True, temperature=0.7
9. yield token                  → Stream each content delta to client
10. _save_message(assistant)    → Persist full response to Postgres
```

**5 Tools with failure shields:**

| Tool | Endpoint / Service | Shield Behavior |
|---|---|---|
| `classify_issue` | `POST {modelserver_url}/classify` | Catches all exceptions → returns `ToolFailure` JSON string |
| `extract_entities` | `POST {modelserver_url}/ner` | Same |
| `summarize_thread` | `POST {modelserver_url}/summarize` | Same |
| `search_knowledge_base` | `RAGService.query()` internally | Same |
| `write_memory` | `write_long_term()` from `memory.py` | Same |

No tool failure can crash the chat loop — the LLM always receives a clean error result and can continue reasoning.

### 7.4 Chat API Router (`app/api/routers/chat.py`)
- **`POST /chat/message`** — JWT-authenticated. Instantiates all service dependencies per request via DI, streams tokens as `StreamingResponse(text/plain)`. First yielded line is always `CONVERSATION_ID:{id}` so clients can track dynamic session IDs.
- **`GET /chat/conversations/{id}`** — Returns `ConversationDetailResponse` with full ordered message history. Enforces ownership (raises `PermissionDenied` if `conversation.user_id != current_user.id`).
- Both endpoints registered in `app/main.py` under prefix `/chat`.

### 7.5 Integration Tests (`tests/test_chatbot.py`)
Full E2E flow verified:
1. Register new user → `201`
2. Login → JWT token
3. `POST /chat/message` without token → `401`
4. `POST /chat/message` with token → `200`, streaming body contains `CONVERSATION_ID:{id}` + LLM tokens
5. LLM autonomously called `classify_issue` tool; response cited **"bug"** / **"classification"**
6. `GET /chat/conversations/{id}` → `200`, `messages[0].role == "user"`, `messages[1].role == "assistant"`

---

## 8. Test Suite Status

**All 27 tests passing** (`pytest`, 118.98s):

| File | Tests | Status |
|---|---|---|
| `tests/test_auth.py` | 1 | ✅ |
| `tests/test_exceptions.py` | 9 | ✅ |
| `tests/test_onnx_classifier.py` | 1 | ✅ |
| `tests/test_rag_pipeline.py` | 1 | ✅ |
| `tests/test_chatbot.py` | 1 | ✅ |
| `tests/test_redaction.py` | 13 | ✅ |
| **Total** | **27** | **✅ 100%** |

---

## 9. Recent Major Architectural Changes

### PyTorch Elimination & ONNX `fastembed` Migration
To optimize the development environment, significantly reduce Docker image sizes (avoiding 2GB+ PyTorch binaries), and allow the backend to run lightweight on CPU, **PyTorch was completely removed** from the dependency tree for the memory and RAG embedding layers. 

**Detailed Changes:**
1. **Library Replacement**: `sentence-transformers` was removed from `requirements.txt` and replaced with `fastembed` (version `0.5.1+`). `fastembed` relies purely on ONNX Runtime for inference.
2. **Model Loading Updates**: In `app/main.py`, the embedding model initialization was updated to use `fastembed.TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")`.
3. **Retrieval API Update**: In `app/services/retrieval.py` and `app/services/memory.py`, embedding generation was adapted to consume the Python generator output yielded by `fastembed.embed()`.
4. **Cross-Encoder Fallback**: Because `fastembed`'s `TextCrossEncoder` is not available without a PyTorch installation in older versions, `app/services/reranker.py` was refactored to gracefully handle `model=None`. When the cross-encoder is disabled, the reranking layer correctly falls back to sorting by the existing RRF (Reciprocal Rank Fusion) hybrid retrieval score.

---

## 10. Completed Memory Layer Implementation (Phases 4.4 & 4.5)

### Phase 4.4 — Short-Term Memory (Redis)
- **Implementation**: Created `app/infra/redis_client.py` using `redis.asyncio.Redis` as the cache provider.
- **Workflow**:
  - `get_conversation_history`: Retrieves messages from `conversations:{id}` using LRANGE.
  - On a cache miss, the system loads the conversation history from PostgreSQL and backfills the Redis cache.
  - `append_message`: Pushes new messages to Redis (`RPUSH`) synchronously with database writes.
- **Optimization**: A strict Time-To-Live (TTL) of **3600 seconds (1 hour)** is enforced via an `EXPIRE` command on every cache append. This prevents temporal conversational bloat in memory. If a session expires, the database serves as the persistent fallback.

### Phase 4.5 — Long-Term Memory (`pgvector`)
- **Implementation**: Developed `app/services/memory.py` utilizing the `TextEmbedding` interface.
- **Workflow**:
  - `write_long_term()`: Generates a dense vector via `fastembed` and inserts it into the `long_term_memories` table along with standard redaction processing and audit logs.
  - `recall_relevant()`: Semantically searches the vector database using `embedding <=> query_embedding LIMIT 5`.
- **System Injection**: Long-term memory recall is explicitly hooked into the `ChatbotService` core loop. Every incoming message performs a semantic search to extract relevant user facts/preferences, dynamically appending them to the System Prompt.
- **LLM Tool**: The LLM autonomously triggers the `write_memory` function call when explicitly instructed by the user to "remember" or "memorize" a detail. Tested successfully via a targeted system prompt update.

---

## 11. What is Left to Implement (Phases 4.6 → 4.8)

### Phase 4.6 — Streamlit App (`chatbot/app.py`)
- **Login screen:** email/password → `/auth/login` → JWT in `st.session_state`.
- **Chat screen:** streaming `POST /chat/message`, conversation history display.
- **Memory Inspector:** list/delete long-term memories.
- **Widget Config** (admin only): create/edit widgets, show embed snippet.

### Phase 4.7 — Widget Config API (`app/api/routers/widgets.py`)
- `POST /widgets` (admin) — create widget record.
- `GET /widgets/{id}` (admin) — fetch config.
- `PATCH /widgets/{id}` (admin) — update.
- `DELETE /widgets/{id}` (admin) — soft-delete.

---

## 12. Engineering Standards & Guidelines

Maintain the following across all future sessions:

| Standard | Rule |
|---|---|
| **Async everywhere** | Never use `requests`, `time.sleep`, or sync DB calls inside ASGI. Use `httpx.AsyncClient`, `asyncio.sleep`, `AsyncSession`. |
| **Dependency Injection** | Inject all singletons via FastAPI `Depends()` or from `request.app.state`. Never instantiate models globally at module import time. |
| **Redaction Gate** | Run `redact()` before logging, writing spans, or saving to memory/DB. |
| **Refuse-to-Boot** | Validate critical dependencies (Vault, model weights) synchronously in lifespan startup. |
| **OTel Spans** | Every service method gets a child span. Include input/output attributes. |
| **Tool Failure Shield** | All external HTTP calls in tool handlers are wrapped in `try/except` returning a clean `ToolFailure` dict — never raise into the chat loop. |
| **No data in Git** | `data/`, `models/*.safetensors`, `.env` are all in `.gitignore`. |
