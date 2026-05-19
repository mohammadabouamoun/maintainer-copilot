# Step by Step Tasks
# Maintainer's Copilot — Step-by-Step Implementation Plan

---

## Pre-Flight Checklist (Before You Write a Line of Code)

- [x] **Choose your open-source repo.** Pick one with ≥500 closed, labelled issues (e.g., `fastapi/fastapi`, `huggingface/transformers`, `pallets/flask`, `pytorch/pytorch`). You will live with this choice all week.
- [x] **Create `DECISIONS.md`** at the repo root immediately. Add your dataset choice and label-mapping logic as your very first commit entry.
- [x] **Confirm your label mapping.** Map repo-native labels → `bug | feature | docs | question`. Document the mapping in `DECISIONS.md` before you touch any data.
- [x] **Clone or init the repo.** Name it something like `maintainers-copilot`.
- [x] **Verify local tooling:** Docker Desktop (with Compose v2), Python 3.11+, Node 20+, `uv` or `pip`, `pre-commit`.
- [x] **Create `.env.example`** with all required variables listed (values redacted). This is what graders run first.

---

## Day 1 — Monday: Foundations

**Goal:** Everything compiles, all services start, secrets flow through Vault, tracing emits spans, and the dataset is on disk with clean splits.

---

### 1.1 Repo Skeleton

- [x] Create the directory tree:
  ```
  app/
    api/          # FastAPI routers only
    services/     # Business logic
    repositories/ # SQL only
    domain/       # Pydantic models
    infra/        # Vault, MinIO, Redis, tracing, redaction adapters
  modelserver/    # Separate FastAPI app for ML inference
  chatbot/        # Streamlit app
  widget/         # React app (Vite)
  demo/host/      # Static host page
  prompts/        # All LLM prompt templates as .txt/.jinja2 files
  migrations/     # Alembic versions
  evals/
    golden_sets/  # classification_golden.json, rag_golden.json
    eval_thresholds.yaml
  .github/workflows/ci.yml
  docker-compose.yml
  .env.example
  DECISIONS.md
  SECURITY.md
  ARCH.md
  ```
- [x] **Verify:** `ls` shows the tree. Commit as `chore: repo skeleton`.

---

### 1.2 Docker Compose — All Services

- [x] Write `docker-compose.yml` with all 10 services. Use health checks and `depends_on` conditions:
  ```yaml
  # Key patterns:
  # - migrate depends_on db (healthy), exits with code 0
  # - api depends_on migrate (completed), vault (healthy), db (healthy), redis (healthy)
  # - chatbot depends_on api (healthy)
  # - modelserver is independent (api calls it over HTTP)
  ```
- [x] Pin image versions:
  - `postgres:16-alpine` with `pgvector/pgvector:pg16`
  - `redis:7-alpine`
  - `minio/minio`
  - `hashicorp/vault` (dev mode: `VAULT_DEV_ROOT_TOKEN_ID` from `.env`)
- [x] Set `PYTHONPATH=/app` and mount `./app:/app` for hot-reload in dev.
- [x] **Verify:** `docker-compose up db redis minio vault` — all four start and health-check green. Check with `docker-compose ps`.

---

### 1.3 Vault Wiring

- [ ] In `app/infra/vault.py`, write a `VaultClient` that:
  - Reads `VAULT_ADDR` and `VAULT_ROOT_TOKEN` from environment
  - Exposes `get_secret(path: str) -> str`
  - Raises a custom `VaultUnavailableError` if the Vault HTTP call fails
- [ ] Write a startup hook in `app/main.py` (FastAPI lifespan) that calls `VaultClient().ping()` on startup and raises if it fails — **this is the "refuse to boot" for Vault** (spec: § "Refuse to Boot").
- [ ] Pre-populate Vault in dev mode with a `scripts/vault_init.sh`:
  ```bash
  vault kv put secret/app \
    llm_api_key="placeholder" \
    jwt_secret="dev-secret-change-me" \
    db_password="postgres" \
    minio_secret="minioadmin" \
    tracing_key="placeholder"
  ```
- [ ] Run the script as part of `docker-compose up` (use a `vault-init` one-shot service or a `command:` in the vault service).
- [ ] **Verify:** `docker-compose exec api python -c "from app.infra.vault import VaultClient; print(VaultClient().get_secret('secret/app/llm_api_key'))"` — prints the value.

---

### 1.4 Database + Alembic

- [ ] Install `alembic`, `sqlalchemy`, `psycopg2-binary`, `pgvector`.
- [ ] Create `migrations/env.py` pointing at `DATABASE_URL` from environment.
- [ ] Write the initial migration (`alembic revision --autogenerate -m "baseline"`) with tables:
  - `users` — id, email, hashed_password, role (`user` | `admin`), created_at
  - `conversations` — id, user_id, created_at
  - `messages` — id, conversation_id, role, content, created_at
  - `long_term_memories` — id, user_id, memory_type, content, embedding (vector), created_at
  - `audit_log` — id, actor_id, action, target, timestamp
  - `widgets` — id, widget_id (uuid), allowed_origins (text[]), theme (jsonb), greeting, enabled_tools (text[]), created_by, created_at
- [ ] Enable pgvector: add `CREATE EXTENSION IF NOT EXISTS vector;` in a migration.
- [ ] **Verify:** `docker-compose run migrate` exits 0. `docker-compose exec db psql -U postgres -c "\dt"` lists all tables.

---

### 1.5 Tracing Wiring (Day 1 — non-negotiable)

- [ ] Choose your tracing backend now and document the choice in `DECISIONS.md`. Recommended options:
  - **Jaeger** (free, self-hosted, OpenTelemetry-native) — simplest for a solo project
  - **Langfuse** (LLM-aware, has a free tier) — better for LLM span attributes
- [ ] Add the tracing service to `docker-compose.yml`.
- [ ] In `app/infra/tracing.py`, write a `setup_tracing()` function using the OpenTelemetry SDK that configures the exporter. Call it in the FastAPI lifespan.
- [ ] Write a `trace_span(name: str)` context manager decorator that all service-layer functions will use.
- [ ] **Verify:** Start the stack, hit `GET /health`, open the trace UI, confirm a span is visible.

---

### 1.6 Dataset Fetch and Splits

- [ ] Write `scripts/fetch_issues.py` using the GitHub REST API (`/repos/{owner}/{repo}/issues?state=closed&labels=...`). Paginate until you have ≥500 labelled issues.
- [ ] Store raw issues as JSONL in `data/raw/issues.jsonl`. Each record: `id, title, body, labels, created_at, closed_at`.
- [ ] Write `scripts/build_splits.py`:
  - Map labels to `bug | feature | docs | question` per your `DECISIONS.md` mapping
  - Filter out issues that don't map cleanly
  - Sort by `created_at`
  - **Stratified split**: 70% train, 15% val, 15% test — but the test set must be strictly more recent than train/val (time-based cutoff first, then stratify within each half)
  - Write `data/splits/train.jsonl`, `val.jsonl`, `test.jsonl`
  - Log class distribution for each split
- [ ] **Verify:** Run `python scripts/build_splits.py`. Print class counts per split. Check that `min(test.created_at) > max(train.created_at)`.

---

### 1.7 Start Fine-Tuning (Background Job)

- [ ] Write `modelserver/train_classifier.py` using HuggingFace `Trainer`:
  - Model: `distilbert-base-uncased` or `roberta-base`
  - Input: `title + " [SEP] " + body[:512]`
  - Labels: 4-class
  - Logger: MLflow or W&B (document choice in `DECISIONS.md`)
  - Save to `models/classifier/`
- [ ] **Start training before you go to sleep Monday night.** Even if the script isn't perfect, get it running. You will iterate Tuesday morning.
- [ ] **Verify:** Script starts without error. Run logger shows a live experiment.

---

## Day 2 — Tuesday: Deep Learning Track

**Goal:** All three classifiers trained and compared. NER and summarizer endpoints live.

---

### 2.1 Finish Fine-Tuned Transformer

- [ ] Wait for (or resume) training from Day 1.
- [ ] Evaluate on `test.jsonl`: compute accuracy, macro-F1, per-class F1.
- [ ] Write `models/classifier/model_card.json`:
  ```json
  {
    "architecture": "distilbert-base-uncased",
    "num_labels": 4,
    "label_map": {"bug": 0, "feature": 1, "docs": 2, "question": 3},
    "hyperparameters": {"lr": 2e-5, "epochs": 3, "batch_size": 16},
    "training_data_hash": "<sha256 of train.jsonl>",
    "freeze_policy": "all encoder layers unfrozen after epoch 0",
    "final_metrics": {"accuracy": 0.0, "macro_f1": 0.0}
  }
  ```
- [ ] Compute `sha256sum models/classifier/pytorch_model.bin` and store it in the model card. This hash is what the API checks on boot (spec: § "Refuse to Boot").
- [ ] Upload model artifacts to MinIO bucket `model-artifacts/classifier/`.
- [ ] Document freeze policy in `DECISIONS.md`.
- [ ] **Verify:** Load the model in a Python REPL and classify three hand-written examples. Results make sense.

---

### 2.2 Classical ML Baseline

- [ ] Write `modelserver/train_classical.py`:
  - Features: TF-IDF on `title + body` (try unigrams + bigrams, min_df=2)
  - Model: `LogisticRegression(max_iter=1000)` or LinearSVC
  - Same train/val/test splits
  - Log metrics to the same run logger
- [ ] Evaluate on `test.jsonl`. Record accuracy, macro-F1, per-class F1, latency (avg inference time per sample), cost (essentially $0 — note that).
- [ ] Save model with `joblib.dump` to `models/classical/`.
- [ ] **Verify:** `python -c "import joblib; m=joblib.load('models/classical/model.pkl'); print(m.predict(['my app crashes on startup']))"`.

---

### 2.3 LLM Baseline

- [ ] Write `scripts/eval_llm_baseline.py`:
  - For each issue in `test.jsonl`, call your LLM with a zero-shot or few-shot prompt asking for `bug | feature | docs | question`
  - Parse the response (strip whitespace, lowercase, map to label)
  - Compute accuracy, macro-F1, per-class F1
  - Record latency (total and per-sample) and cost (token counts × price)
- [ ] Store results in `evals/llm_baseline_results.json`.
- [ ] **Verify:** Script runs to completion. Check that parsed labels are all in the 4-class set (no "unknown" sneaking through).

---

### 2.4 Three-Way Comparison in DECISIONS.md

- [ ] Add a section `## Classifier Comparison` to `DECISIONS.md` with a markdown table:
  ```
  | Model           | Accuracy | Macro-F1 | Bug F1 | Feature F1 | Docs F1 | Question F1 | Latency (ms) | Cost/1k |
  |-----------------|----------|----------|--------|------------|---------|-------------|--------------|---------|
  | Classical ML    |          |          |        |            |         |             |              | ~$0     |
  | Fine-tuned XFMR |          |          |        |            |         |             |              | ~$0     |
  | LLM baseline    |          |          |        |            |         |             |              |         |
  ```
- [ ] Write one paragraph defending your deployment choice with explicit reference to scale, latency budget, and failure cost scenarios.
- [ ] **Verify:** A colleague reading only this section could reproduce your deployment decision.

---

### 2.5 ModelServer — Classifier Endpoint

- [ ] In `modelserver/main.py` (a separate FastAPI app), add:
  ```python
  POST /classify
  Body: {"text": str}
  Response: {"label": str, "confidence": float, "latency_ms": float}
  ```
- [ ] Load the deployed model at startup (document which one in `DECISIONS.md`).
- [ ] Verify the SHA-256 of the weights file against the model card on startup. Refuse to start if mismatch (spec: § "Refuse to Boot").
- [ ] Wrap in a tracing span: `classify_span` with attributes `model_name`, `input_length`, `predicted_label`, `latency_ms`.
- [ ] **Verify:** `curl -X POST http://localhost:8001/classify -H 'Content-Type: application/json' -d '{"text":"app crashes on import"}'` returns `{"label":"bug","confidence":0.92,"latency_ms":12}`.

---

### 2.6 ModelServer — NER Endpoint

- [ ] Integrate a pre-trained NER pipeline (e.g., `spaCy en_core_web_sm` or HuggingFace `dslim/bert-base-NER`).
- [ ] Post-process to extract code-shaped entities: version strings (`v1.2.3`), error codes (`HTTP 500`, `ENOENT`), package names, function-like tokens (`foo_bar()`).
- [ ] Endpoint:
  ```python
  POST /ner
  Body: {"text": str}
  Response: {"entities": [{"text": str, "label": str, "start": int, "end": int}]}
  ```
- [ ] **Verify:** Send a real GitHub issue body. The response contains at least version numbers and error-looking strings.

---

### 2.7 ModelServer — Summarizer Endpoint

- [ ] Use a pre-trained summarization pipeline (e.g., `facebook/bart-large-cnn`) or an LLM call with a concise prompt.
- [ ] Endpoint:
  ```python
  POST /summarize
  Body: {"text": str, "max_length": int = 150}
  Response: {"summary": str}
  ```
- [ ] If using an LLM call, load the prompt from `prompts/summarize.txt` — never inline it.
- [ ] **Verify:** Send a 20-message issue thread. The summary is ≤ 150 words and captures the key problem.

---

### 2.8 Classification Golden Set (25 Examples)

- [ ] Create `evals/golden_sets/classification_golden.json` — 25 hand-picked issues (not in train/val/test splits if possible, or explicitly noted if overlapping with test):
  ```json
  [
    {"id": "1", "text": "...", "expected_label": "bug"},
    ...
  ]
  ```
- [ ] Write `evals/run_classification_eval.py` that loads all three models, runs them against the golden set, and writes `evals/eval_report_classification.json` with macro-F1, per-class F1, confusion matrix per model.
- [ ] **Verify:** `python evals/run_classification_eval.py` exits 0 and writes the report file.

---

## Day 3 — Wednesday: Advanced RAG

**Goal:** RAG pipeline beating the baseline on the golden set. Redaction layer live and tested.

---

### 3.1 Corpus Preparation

- [ ] Collect corpus documents:
  - Project documentation (scrape with `requests` + `BeautifulSoup`, or clone the `docs/` folder from the repo)
  - Held-out resolved issues with maintainer answers (a slice of closed issues NOT used in classifier training, where the accepted answer / closing comment is the "ground truth answer")
- [ ] Write `scripts/preprocess_corpus.py`. Your preprocessing pipeline must be documented and defended in `DECISIONS.md`. Consider:
  - Strip HTML tags, normalize whitespace
  - Split docs by section headers (for docs pages)
  - For issues: include title + body + closing comment, strip code blocks > N lines (or keep with a `type=code` metadata tag)
- [ ] Write to `data/corpus/docs.jsonl` and `data/corpus/resolved_issues.jsonl`.
- [ ] **Verify:** Spot-check 5 random records. No raw HTML. Section boundaries make sense.

---

### 3.2 Embedding Model Choice

- [ ] Choose a primary embedding model and one alternative. Candidates:
  - `BAAI/bge-base-en-v1.5` (strong general-purpose)
  - `sentence-transformers/all-MiniLM-L6-v2` (fast, smaller)
  - `text-embedding-3-small` (OpenAI, API-based)
- [ ] Write `scripts/compare_embeddings.py` that embeds all corpus chunks with both models, builds two in-memory indexes, and evaluates retrieval quality (hit@5, MRR@10) against a small 10-question probe set you write manually.
- [ ] Document the winner and the numbers in `DECISIONS.md` under `## Embedding Model Choice`.
- [ ] **Verify:** The comparison script outputs a table. The winning model's hit@5 is meaningfully better (or you justify keeping the cheaper one if delta is < 1%).

---

### 3.3 Chunking Strategy

- [ ] Implement a non-naive chunking strategy. Options (pick one, document it):
  - **Semantic chunking:** Split when cosine distance between adjacent sentences exceeds a threshold
  - **Structure-aware:** Split on markdown headings + paragraph breaks; keep code blocks intact
  - **Recursive character text splitter** with overlap, tuned per content type (docs vs issues)
- [ ] Store chunks in Postgres (pgvector table) AND in MinIO as a snapshot for reproducibility.
  ```sql
  CREATE TABLE corpus_chunks (
    id UUID PRIMARY KEY,
    source_type TEXT,  -- 'doc' | 'issue'
    source_id TEXT,
    chunk_index INT,
    content TEXT,
    metadata JSONB,    -- section, url, labels, created_at
    embedding vector(768)
  );
  ```
- [ ] Write `scripts/ingest_corpus.py` that chunks, embeds, and upserts into the table.
- [ ] **Verify:** `SELECT COUNT(*) FROM corpus_chunks;` returns a non-zero number. Spot-check 3 chunks manually.

---

### 3.4 Hybrid Retrieval

- [ ] **Dense retrieval:** pgvector `<=>` cosine distance query returning top-k by embedding similarity.
- [ ] **Sparse retrieval:** Either use `tsvector` full-text search in Postgres, or stand up a BM25 index using `rank_bm25` or Elasticsearch (if you want to keep the stack simple, Postgres FTS is sufficient).
- [ ] **Fusion:** Implement Reciprocal Rank Fusion (RRF) or a weighted linear combination. Tune the weight (α for dense, 1-α for sparse) on the RAG golden set and document the winning α.
- [ ] Put this logic in `app/services/retrieval.py` with a clean interface:
  ```python
  def hybrid_retrieve(query: str, top_k: int = 20, metadata_filter: dict = None) -> list[Chunk]
  ```
- [ ] **Verify:** Call the function from a Python REPL with a known question. Top results are relevant. Time the call — it should be < 500ms.

---

### 3.5 Cross-Encoder Reranking

- [ ] Install `sentence-transformers`. Use `cross-encoder/ms-marco-MiniLM-L-6-v2` or similar.
- [ ] Write `app/services/reranker.py`:
  ```python
  def rerank(query: str, chunks: list[Chunk], top_n: int = 5) -> list[Chunk]
  ```
- [ ] Call `hybrid_retrieve(top_k=20)` then `rerank(top_n=5)`.
- [ ] **Verify:** Pick a query where the naive top-1 is wrong. Show the reranker promotes the right chunk. Document the example in `DECISIONS.md`.

---

### 3.6 Query Transformation

- [ ] Implement one technique (document your choice in `DECISIONS.md`):
  - **HyDE (Hypothetical Document Embeddings):** Ask the LLM to generate a hypothetical ideal answer, embed that, retrieve
  - **Query rewriting:** Ask the LLM to rewrite the user's question into a more retrieval-friendly form
  - **Multi-query:** Generate 3 query variants, retrieve for each, union + deduplicate
- [ ] Apply the transformation before calling `hybrid_retrieve`.
- [ ] Write a prompt file `prompts/query_rewrite.txt` (or similar). Never inline prompts.
- [ ] **Verify:** Test with a vague question like "why does it not work with Python 3.12". The transformed query is more specific and returns better chunks.

---

### 3.7 RAG Golden Set and Eval

- [ ] Create `evals/golden_sets/rag_golden.json` — 25 triples:
  ```json
  [
    {
      "id": "1",
      "question": "How do I configure the timeout for HTTP connections?",
      "ideal_answer": "Set the `timeout` parameter in ...",
      "ground_truth_chunk_ids": ["uuid-1", "uuid-2"]
    },
    ...
  ]
  ```
- [ ] Hand-label 5 of the 25 yourself (write the ideal answer from memory/docs, before running the pipeline). Record your labels separately.
- [ ] Write `evals/run_rag_eval.py` using RAGAS or a frozen judge model:
  - Retrieval: hit@5 (is a ground-truth chunk in top 5?), MRR@10
  - Generation: faithfulness (does the answer stay grounded in retrieved chunks?), answer relevancy
  - Report agreement between your 5 hand labels and the judge model's scores
- [ ] Set thresholds in `eval_thresholds.yaml`:
  ```yaml
  classification:
    macro_f1: 0.75  # example — set to your actual Day 2 result minus a small buffer
  rag:
    hit_at_5: 0.70
    faithfulness: 0.75
    answer_relevancy: 0.70
  ```
- [ ] **Verify:** `python evals/run_rag_eval.py` writes `evals/eval_report_rag.json`. All metrics are above threshold.

---

### 3.8 Redaction Layer

- [ ] Write `app/infra/redaction.py`:
  ```python
  PATTERNS = [
    (r'sk-[A-Za-z0-9]{20,}', '[REDACTED_API_KEY]'),
    (r'ghp_[A-Za-z0-9]{36}', '[REDACTED_GH_TOKEN]'),
    (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[REDACTED_EMAIL]'),
    (r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b', '[REDACTED_CARD]'),
    # Add more — think about what appears in real issue text
  ]

  def redact(text: str) -> str: ...
  ```
- [ ] Document and defend all patterns in `SECURITY.md`. Think carefully: what real-world tokens appear in GitHub issue text?
- [ ] Apply `redact()` in:
  - Every structured log call (wrap the Python logging formatter)
  - Every OpenTelemetry span attribute setter
  - Every long-term memory write (in `app/services/memory.py`)
- [ ] Write a test `tests/test_redaction.py`:
  ```python
  def test_api_key_never_logged(caplog):
      text = "I set API_KEY=sk-abc123xyz456def789ghi012 and it crashed"
      redacted = redact(text)
      assert "sk-abc123xyz456def789ghi012" not in redacted
      assert "[REDACTED_API_KEY]" in redacted
  ```
- [ ] **Verify:** `pytest tests/test_redaction.py` passes. Check that the test would fail if you removed the pattern.

---

### 3.9 Exception Handling Refactor

- [ ] Create `app/domain/exceptions.py`:
  ```python
  class AppError(Exception):
      def __init__(self, message: str, code: str): ...

  class NotFoundError(AppError): ...
  class PermissionDenied(AppError): ...
  class ToolFailure(AppError): ...
  class VaultUnavailableError(AppError): ...
  class ModelServerError(AppError): ...
  ```
- [ ] Add a single exception handler in `app/api/main.py`:
  ```python
  @app.exception_handler(AppError)
  async def app_error_handler(request, exc):
      return JSONResponse(
          status_code=exc.http_status,
          content={"error": exc.code, "message": exc.message, "request_id": request.state.request_id}
      )
  ```
- [ ] Ensure every unhandled exception is caught, logged with trace_id + request_id, and returns a generic 500 with request_id but no stack trace.
- [ ] **Verify:** Hit a non-existent endpoint. The response is `{"error": "NOT_FOUND", "message": "...", "request_id": "..."}`. No stack trace.

---

## Day 4 — Thursday: Chatbot + Memory + Embed

**Goal:** The full chatbot works. The widget embeds in the host app. Both eval suites run in CI.

> ⚠️ This is the heaviest day. Start early. Do auth first (everything else depends on it).

---

### 4.1 Authentication (fastapi-users)

- [ ] Install `fastapi-users[sqlalchemy]`.
- [ ] Configure with SQLAlchemy backend, JWT strategy. **JWT signing key must resolve from Vault** — not from `.env`.
- [ ] Implement `user` and `admin` roles. Add role to the JWT payload.
- [ ] Expose:
  - `POST /auth/register` (admin-only invite flow, or open for dev)
  - `POST /auth/login` → returns JWT
  - `GET /users/me` → returns current user
- [ ] Write a role-check dependency:
  ```python
  def require_role(role: str):
      async def dep(user=Depends(current_active_user)):
          if user.role != role: raise PermissionDenied(...)
          return user
      return dep
  ```
- [ ] **Verify:** Register a user, log in, get a JWT, hit `/users/me` with the Bearer token. Then hit an admin endpoint without admin role — get 403.

---

### 4.2 RAG Endpoint

- [ ] In `app/api/routers/rag.py`:
  ```
  POST /rag/query
  Auth: JWT required
  Body: {"question": str, "conversation_id": str | None, "metadata_filter": dict | None}
  Response: {"answer": str, "chunks": [...], "trace_id": str}
  ```
- [ ] Wire to `app/services/rag_service.py` which orchestrates: transform query → hybrid retrieve → rerank → generate answer (LLM call with context + prompt from `prompts/rag_answer.txt`).
- [ ] Every sub-step is a child span under the parent `rag_query` span.
- [ ] Retrieved chunks snapshot saved to MinIO as `chunks/{conversation_id}/{timestamp}.json`.
- [ ] **Verify:** `curl -X POST .../rag/query -H "Authorization: Bearer ..." -d '{"question":"how do I install the package"}'` returns a grounded answer.

---

### 4.3 Chatbot Service — Tool-Calling LLM

- [ ] In `app/services/chatbot.py`, implement the core loop:
  ```python
  async def chat(conversation_id, user_message, user_id) -> AsyncIterator[str]:
      # 1. Load short-term memory from Redis
      # 2. Load relevant long-term memories
      # 3. Build system prompt from prompts/system.txt
      # 4. Construct messages array with history
      # 5. Call LLM with tools defined (below)
      # 6. If tool_call: dispatch to tool, append tool result, loop
      # 7. Stream final response
      # 8. Save message to DB
  ```
- [ ] Define tools for the LLM:
  ```python
  tools = [
    {"name": "classify_issue", "description": "...", "parameters": {...}},
    {"name": "extract_entities", "description": "...", "parameters": {...}},
    {"name": "summarize_thread", "description": "...", "parameters": {...}},
    {"name": "search_knowledge_base", "description": "...", "parameters": {...}},
    {"name": "write_memory", "description": "Write a fact to long-term memory. Only call when explicitly asked.", "parameters": {...}},
  ]
  ```
- [ ] Each tool function calls the appropriate service or ModelServer endpoint over HTTP. Wrap in try/except → return `ToolFailure` message (never crash the chat loop).
- [ ] Expose `POST /chat/message` (streaming with `StreamingResponse`) and `GET /chat/conversations/{id}`.
- [ ] **Verify:** Send "Classify this issue: app crashes on startup" to the chat endpoint. The LLM calls `classify_issue`, gets a result, and streams back a response citing the classification.

---

### 4.4 Short-Term Memory (Redis)

- [ ] In `app/infra/redis_client.py`, wrap `redis.asyncio.Redis`.
- [ ] In `app/services/memory.py`:
  ```python
  async def get_conversation_history(conversation_id: str) -> list[Message]:
      # LRANGE conversations:{id} 0 -1
  
  async def append_message(conversation_id: str, message: Message, ttl_seconds: int = 3600):
      # RPUSH + EXPIRE
  ```
- [ ] **Justify the TTL in `DECISIONS.md`**: Why 1 hour? What happens when the TTL expires mid-conversation? What is the fallback (load from Postgres)?
- [ ] **Verify:** Send 3 messages. `docker-compose exec redis redis-cli LRANGE conversations:test-id 0 -1` shows the messages. Wait for TTL, verify they're gone.

---

### 4.5 Long-Term Memory (pgvector)

- [ ] In `app/services/memory.py`, add:
  ```python
  async def write_long_term(user_id, content: str, memory_type: str, actor_id):
      embedding = embed(content)
      # INSERT INTO long_term_memories
      # INSERT INTO audit_log (actor, action='memory_write', target=memory_id, timestamp)

  async def recall_relevant(user_id, query: str, top_k: int = 5) -> list[Memory]:
      embedding = embed(query)
      # SELECT ... ORDER BY embedding <=> $1 LIMIT $2
  ```
- [ ] Document your memory type choice (episodic / semantic / procedural) and rationale in `DECISIONS.md`.
- [ ] The `write_memory` LLM tool calls `write_long_term`. **No other code path writes long-term memory automatically** (spec: § "Memory").
- [ ] **Verify:** Tell the chatbot "Remember that I prefer concise answers." Call the `write_memory` tool explicitly. Query `SELECT * FROM long_term_memories;` — the row is there. Send a new conversation — the memory is loaded and affects the response.

---

### 4.6 Streamlit App

- [ ] Create `chatbot/app.py`. Screens:
  - **Login** — email + password → calls `/auth/login` → stores JWT in `st.session_state`
  - **Chat** — calls `/chat/message` (streaming), displays conversation history
  - **Memory Inspector** (admin + user) — lists long-term memories for current user, allows deletion
  - **Widget Config** (admin only) — form to create/edit widget records, shows embed snippet
- [ ] Load the FastAPI base URL from an env var (`API_URL`).
- [ ] **Verify:** Open Streamlit, log in, send a message, see the streamed response, open the memory inspector.

---

### 4.7 Widget Config API

- [ ] In `app/api/routers/widgets.py`:
  ```
  POST   /widgets           (admin only) — create widget
  GET    /widgets/{id}      (admin only) — get config
  PUT    /widgets/{id}      (admin only) — update config
  GET    /widgets/{id}/public — no auth, returns {theme, greeting, enabled_tools}
  ```
- [ ] CORS for the widget iframe comes from `allowed_origins` in the widget DB row — not a hardcoded env var.
- [ ] Add `Content-Security-Policy: frame-ancestors {origins}` to the response headers for the embed route (spec: § "Origin Allowlisting").
- [ ] **Verify:** Create a widget via the Streamlit admin page. Query `/widgets/{id}/public` — returns config. Change `allowed_origins` — verify the CSP header changes accordingly.

---

### 4.8 React Widget

- [ ] `cd widget && npm create vite@latest . -- --template react-ts`
- [ ] Implement components:
  - `ChatBubble` — collapsed floating button
  - `ChatPanel` — expands on click, shows message list
  - `MessageInput` — input + send button
  - `StreamingMessage` — handles SSE / streamed response
- [ ] On mount, fetch `/widgets/{WIDGET_ID}/public` to get theme + greeting.
- [ ] Apply theme CSS variables dynamically:
  ```javascript
  document.documentElement.style.setProperty('--primary-color', config.theme.primary_color);
  ```
- [ ] Implement `postMessage` to parent for iframe resize:
  ```javascript
  window.parent.postMessage({type: 'resize', height: document.body.scrollHeight}, '*');
  ```
- [ ] `npm run build` — output to `widget/dist/`. The bundle should be a single JS file.
- [ ] **Check bundle size:** `ls -lh widget/dist/assets/*.js`. Record gzipped size: `gzip -c widget/dist/assets/index-*.js | wc -c`. Aim for < 150KB gzipped. If over, lazy-load heavy dependencies.
- [ ] **Verify:** Open `widget/dist/index.html` in a browser. The bubble appears. Clicking it opens the chat panel.

---

### 4.9 Loader Script and Host Demo

- [ ] Write `widget/public/widget.js` (the loader script):
  ```javascript
  (function() {
    const script = document.currentScript;
    const widgetId = script.getAttribute('data-widget-id');
    const iframe = document.createElement('iframe');
    iframe.src = `${WIDGET_BASE_URL}/widget/index.html?widget_id=${widgetId}`;
    iframe.style.cssText = 'position:fixed;bottom:20px;right:20px;width:380px;height:600px;border:none;z-index:9999';
    document.body.appendChild(iframe);
    window.addEventListener('message', (e) => {
      if (e.data.type === 'resize') iframe.style.height = e.data.height + 'px';
    });
  })();
  ```
- [ ] Create `demo/host/index.html`:
  ```html
  <!DOCTYPE html>
  <html>
  <body>
    <h1>My Project Docs</h1>
    <p>This page embeds the Maintainer's Copilot widget.</p>
    <script src="http://localhost:8000/widget.js" data-widget-id="YOUR_WIDGET_ID"></script>
  </body>
  </html>
  ```
- [ ] Add an `nginx` container for the host in `docker-compose.yml` serving `demo/host/`.
- [ ] **Verify (allowed host):** Open `http://localhost:9000` (host container). Widget bubble appears. Open browser DevTools → Network — no CORS errors.
- [ ] **Verify (blocked host):** Temporarily add a second host on a different port NOT in `allowed_origins`. Open it. Browser Console shows CSP frame-ancestors violation. No widget appears. Screenshot both for the demo.

---

### 4.10 CI Pipeline

- [ ] Write `.github/workflows/ci.yml`:
  ```yaml
  name: CI
  on: [push]
  jobs:
    ci:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - name: Start stack
          run: docker-compose up -d --build
        - name: Wait for healthy
          run: ./scripts/wait_for_healthy.sh
        - name: Lint
          run: docker-compose exec -T api ruff check app/
        - name: Type-check
          run: docker-compose exec -T api mypy app/
        - name: Redaction test
          run: docker-compose exec -T api pytest tests/test_redaction.py -v
        - name: Classification eval
          run: docker-compose exec -T api python evals/run_classification_eval.py
        - name: RAG eval
          run: docker-compose exec -T api python evals/run_rag_eval.py
        - name: Smoke test
          run: ./scripts/smoke_test.sh
  ```
- [ ] Both eval scripts must exit non-zero if any metric is below the threshold in `eval_thresholds.yaml`. Use:
  ```python
  if metrics['macro_f1'] < thresholds['classification']['macro_f1']:
      sys.exit(1)
  ```
- [ ] Upload `eval_report.json` to MinIO in CI:
  ```python
  minio_client.put_object('eval-reports', f'{git_sha}.json', ...)
  ```
- [ ] **Verify:** Push a commit. GitHub Actions runs. Both eval suites pass. Artificially lower a threshold in `eval_thresholds.yaml` to 0 — CI should fail (spec: § "Refuse to Boot" — zero thresholds are disallowed).

---

## Day 5 — Friday AM: Polish, Integration, and Demo Prep

**Goal:** CI green, demo rehearsed, every required doc written.

---

### 5.1 Refuse-to-Boot Checklist

Verify each condition causes API startup failure with a clear error message (not a cryptic crash):

- [ ] Vault unreachable → `VaultUnavailableError: Cannot connect to Vault at {addr}`
- [ ] Classifier weights missing from MinIO → `ModelArtifactError: weights not found`
- [ ] SHA-256 mismatch → `ModelArtifactError: weights hash mismatch. Expected {x}, got {y}`
- [ ] Tracing backend misconfigured → `TracingError: Cannot connect to {backend}`
- [ ] Any eval threshold set to 0 or disabled in `eval_thresholds.yaml` → `ConfigError: threshold for {metric} is 0 or disabled`

For each: stop Vault (`docker-compose stop vault`), try to start API, confirm the error message, restart Vault.

---

### 5.2 Required Documentation Files

Write or finalize each file. These are graded:

- [ ] **`ARCH.md`** — System architecture overview. Include a diagram (ASCII or Mermaid). Describe every service, every data flow, every inter-service call. Should match the actual code.
- [ ] **`DECISIONS.md`** — One section per major decision with the backing number:
  - Label mapping
  - Freeze policy
  - Three-way classifier comparison + deployment choice
  - Embedding model choice + retrieval quality number
  - Chunking strategy + number vs naive baseline
  - Hybrid retrieval weighting + number
  - Reranker choice
  - Query transformation choice + number
  - Memory type choice (episodic/semantic/procedural) + rationale
  - Redis TTL rationale
  - Tracing backend choice
- [ ] **`RUNBOOK.md`** — How to:
  - Start the stack from scratch
  - Create the first admin user
  - Ingest the corpus
  - Train the classifier
  - Run the evals
  - Roll back a bad deploy
  - What to do when Vault is down
- [ ] **`EVALS.md`** — Describe both golden sets: how they were created, how the thresholds were set, how CI enforces them, the judge model used for RAG, and the 5 hand-labeled examples with agreement score.
- [ ] **`SECURITY.md`** — List every redaction pattern, explain why each is there, and describe where in the stack redaction is applied. Answer: "A user pastes a GitHub token into the chat. Trace every place it could appear without redaction."

---

### 5.3 Final Integration Checks

- [ ] `docker-compose down -v && docker-compose up --build` from scratch — everything comes up, migrations run, API is healthy.
- [ ] Register a user, log in via Streamlit, send a message that triggers all 5 tools in one session.
- [ ] Use `write_memory` explicitly, start a new conversation, verify the memory is recalled.
- [ ] Open the trace UI — find the conversation trace. Confirm span hierarchy: `user_message → [classify_span, ner_span, rag_query_span → [retrieve_span, rerank_span, generate_span], write_memory_span]`.
- [ ] Simulate a tool failure: stop `modelserver`. Send a classification request. The chatbot responds gracefully ("I couldn't classify this issue right now, but here's what I can tell you..."). It does not 500.
- [ ] `grep -ri 'sk-' app/` → zero matches outside `app/infra/vault.py`.
- [ ] `grep -ri 'password' app/` → zero matches outside `app/infra/vault.py`.

---

### 5.4 Demo Rehearsal Script (10 minutes)

Practice this exact flow:

1. **(1 min)** Open `docker-compose ps` — all 10 services healthy. Show `ARCH.md` overview.
2. **(2 min)** Open the Streamlit app. Log in as admin. Create a widget config with the demo host as the only allowed origin. Copy the embed snippet.
3. **(2 min)** Open the demo host in a browser. Widget loads. Send a message that involves at least 2 tool calls (e.g., "Classify this issue and then search the docs for the fix: `RuntimeError` on Python 3.12"). Show streamed response.
4. **(1 min)** Say "Remember that I prefer bullet-point answers." The LLM calls `write_memory`. Show the memory inspector in Streamlit.
5. **(1 min)** Open the trace UI. Walk the trace tree for the last conversation. Point out model name, token count, latency attributes. Show an error-path trace.
6. **(1 min)** Open a second browser tab with a host page on a different port (not in `allowed_origins`). Show the CSP error in DevTools console. Widget does not load.
7. **(1 min)** Evaluator asks you to add a new endpoint or tool live. Make the change, show it respects the layer boundaries (`api/` → `services/` → no direct DB in router).
8. **(1 min)** Show CI green. Artificially lower one threshold — push — show CI fails.

---

### 5.5 Submission Block

Fill in the submission template (`SUBMISSION.md`):

```
Project 7 - [Your Name]
Repo: https://github.com/...
Tag: v0.1.0-week7
Dataset: [chosen repo] issues, [N train / N val / N test]

Classification — Classical: F1=[n] | Fine-tuned: F1=[n] | LLM: F1=[n]
Deployment choice: [model] - because [one line reason]
Embedding model: [name] - chosen because [one line reason]
RAG — hit@5=[n] | MRR@10=[n] | Faithfulness=[n] | Answer relevancy=[n]
Long-term memory type: [episodic | semantic | procedural]
Tracing backend: [name] - chosen because [one line reason]
Widget bundle size: [n] KB (gzipped)
LLM: [provider + model]
README contains: ARCH.md ✓ | DECISIONS.md ✓ | RUNBOOK.md ✓ | EVALS.md ✓ | SECURITY.md ✓
```

- [ ] Tag the commit: `git tag v0.1.0-week7 && git push origin v0.1.0-week7`
- [ ] Fresh-clone test: `git clone ... /tmp/test-clone && cd /tmp/test-clone && cp .env.example .env && # fill in vault token && docker-compose up`. Confirm it works.

---

## Appendix: Key File Reference

| File | Purpose |
|---|---|
| `app/infra/vault.py` | Vault client, raises on unreachable |
| `app/infra/tracing.py` | OTel setup, `trace_span` decorator |
| `app/infra/redaction.py` | Redaction patterns, `redact()` function |
| `app/infra/minio_client.py` | MinIO adapter |
| `app/infra/redis_client.py` | Redis async adapter |
| `app/domain/exceptions.py` | Domain exception hierarchy |
| `app/services/retrieval.py` | Hybrid retrieve + rerank + query transform |
| `app/services/chatbot.py` | Tool-calling LLM loop |
| `app/services/memory.py` | Redis short-term + pgvector long-term |
| `app/repositories/corpus_repo.py` | pgvector chunk queries |
| `app/api/routers/chat.py` | Chat streaming endpoint |
| `app/api/routers/widgets.py` | Widget CRUD + CSP headers |
| `modelserver/main.py` | Classifier + NER + summarizer endpoints |
| `chatbot/app.py` | Streamlit UI |
| `widget/src/` | React widget source |
| `widget/public/widget.js` | Loader script |
| `demo/host/index.html` | Demo host page |
| `prompts/` | All LLM prompts as version-controlled files |
| `evals/golden_sets/` | Hand-curated golden sets |
| `evals/eval_thresholds.yaml` | Committed CI thresholds |
| `evals/run_classification_eval.py` | Classification eval script |
| `evals/run_rag_eval.py` | RAG eval script |
| `migrations/` | Alembic versions |
| `DECISIONS.md` | Every architectural choice + backing number |
| `SECURITY.md` | Redaction patterns + threat model |
| `ARCH.md` | System architecture diagram + service descriptions |
| `RUNBOOK.md` | Operational procedures |
| `EVALS.md` | Eval methodology, golden set provenance, CI gates |

---

## Appendix: "Think About" Questions to Prepare For

These are explicitly listed in the spec and will be asked Friday:

1. **Three models, one production.** Which ships? Does your answer change if scale is 10×? If latency budget drops to 50ms? If a misclassified bug causes a security incident vs just clutter?
2. **Embedding model validation.** Why is your embedding model right for *this corpus*, not just a benchmark?
3. **Judge disagreement.** The LLM judge disagrees with 2 of your 5 hand-labeled RAG examples. Who's right? How do you decide? What do you do with the judge in CI?
4. **Redis TTL boundary.** User starts a conversation, goes to lunch (70 min), comes back. What happens? What should happen? Is that what your code does?
5. **Bundle size pushback.** PM says 180KB gzipped is too big. What do you cut? At what size do you push back?
6. **Token in logs.** User pastes a GitHub token in the chat. Name every place it could end up unredacted. How would you detect the leak?
7. **Slow span.** Trace shows 4.3s span, unknown cause. What's missing from the trace? Why is that a design decision?
8. **Vault down at runtime.** App is already running. Vault goes down. What happens? What *should* happen? Where does the policy live?
