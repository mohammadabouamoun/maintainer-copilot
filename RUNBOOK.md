# Runbook: Operations & Maintenance

This runbook contains operational procedures for running, configuration, auditing, and troubleshooting the **Maintainer's Copilot** platform.

---

## 🚀 1. Starting the Services

To boot the entire service mesh, follow the instructions below.

### Step 1: Start Infrastructure & Static Frontends
Start the supporting services (PostgreSQL, Redis, MinIO, Vault) and Nginx-based host page/React dev server:
```bash
docker compose up -d db redis minio vault migrate widget host
```

### Step 2: Initialize Database and Schema (Optional)
If running for the first time or after a schema update, run the migrations:
```bash
docker compose run --rm migrate
```

### Step 3: Run the ModelServer (Inference Engine)
The ModelServer runs heavy ML pipelines. Run it locally via:
```bash
# Activate virtual environment and set PYTHONPATH
source .venv/bin/activate
PYTHONPATH=. python modelserver/app.py
```
*(By default, it listens on port `8001`)*.

### Step 4: Run the FastAPI Backend
Start the main application API:
```bash
source .venv/bin/activate
PYTHONPATH=. uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
*(By default, it listens on port `8000`)*.

### Step 5: Start the Streamlit Admin Panel
Run the administration portal to configure widgets and inspect memory:
```bash
source .venv/bin/activate
API_URL=http://localhost:8000 streamlit run chatbot/app.py --server.port 8501
```

---

## 🧪 2. Running Evaluation Suites & Tests

We use automated evaluation pipelines to ensure that changes do not degrade classification or RAG performance.

### Run Code Linter & Quality Checks
```bash
ruff check app/ modelserver/ evals/ tests/
mypy app/ --ignore-missing-imports
```

### Run Unit and Integration Tests
```bash
# Run sensitive log redaction verification tests
PYTHONPATH=. pytest tests/test_redaction.py -v

# Run authentication flow tests
PYTHONPATH=. pytest tests/test_auth.py -v
```

### Run Machine Learning Eval Suites
Ensure your infrastructure containers are up and running, then execute the evaluation scripts:
```bash
# Run Classifier F1 metrics evaluation
PYTHONPATH=. python evals/run_classification_eval.py

# Run RAG Hit@5 and LLM faithfulness evaluation
PYTHONPATH=. python evals/run_rag_eval.py
```
*Note: Both evaluation scripts read target thresholds from `evals/eval_thresholds.yaml` and will fail (exit status `1`) if any calculated metric falls below those thresholds.*

---

## ⚙️ 3. Adding a New Validation Threshold

All evaluation gates are driven by `evals/eval_thresholds.yaml`.

### Step-by-Step Guide
1. Open the configuration file [eval_thresholds.yaml](file:///home/usermohammad/maintainer-copilot/evals/eval_thresholds.yaml).
2. Add your new metric name and float value under the relevant service block (e.g. `classification` or `rag`):
   ```yaml
   classification:
     macro_f1: 0.75
     accuracy: 0.70  # New metric threshold
   ```
3. Update the corresponding evaluation script (`run_classification_eval.py` or `run_rag_eval.py`) to calculate the new metric and assert that it meets the threshold:
   ```python
   # Inside run_classification_eval.py
   assert accuracy >= thresholds["classification"]["accuracy"], f"Accuracy below threshold"
   ```

> [!IMPORTANT]
> **Refuse-to-Boot Verification:** 
> Setting a threshold to `0` or leaving it blank/disabled is strictly disallowed. The FastAPI backend and both eval scripts validate this file on startup; if a zero/disabled threshold is detected, they will refuse to boot and throw a `ConfigError: threshold for {metric} is 0 or disabled`.

---

## 🔍 4. Debugging CORS & CSP Issues

If the embedded React widget fails to display on a host website or shows errors in the browser console, follow this troubleshooting guide.

### Symptom: Widget does not load / Empty space where iframe should be
*   **Likely Cause:** Content-Security-Policy (CSP) `frame-ancestors` violation.
*   **Resolution Flow:**
    1. Open the browser's developer console (DevTools → Console). Look for:
       `Refused to frame 'http://localhost:8000/' because an ancestor violates the following Content Security Policy directive: "frame-ancestors..."`
    2. Log into the Streamlit Admin Panel (`http://localhost:8501`).
    3. Navigate to the **Widget Config** tab.
    4. Select your active widget and locate the **Allowed Origins** field.
    5. Ensure the origin of the page loading the widget (e.g. `http://localhost:9000`) is explicitly added to the allowed origins.
    6. Save configuration. The backend will automatically update its CSP headers on the next request to match the updated origin list.

### Symptom: HTTP 403 Forbidden / CORS errors during chat messages
*   **Likely Cause:** The request origin is not permitted by the FastAPI backend.
*   **Resolution Flow:**
    1. In browser DevTools, check the Network tab. If requests to `http://localhost:8000/chat/message` return HTTP `403 Forbidden`, the backend blocked the request.
    2. Check the `Origin` header of the outgoing request.
    3. In the database (via Streamlit admin), confirm that the widget contains that exact `Origin` string inside its `allowed_origins` array.
    4. Ensure the widget initialization script tag has the correct `data-widget-id` matching the database entry.

---

## 🔑 5. Creating the First Admin User

To create the initial admin user to log into the Streamlit admin panel, send a POST request to the API registration endpoint with `"role": "admin"`:

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "your_secure_password_here",
    "role": "admin"
  }'
```

---

## 🗄️ 6. Ingesting the RAG Corpus

If documentation or issues have updated, ingest the corpus snapshot to PostgreSQL vector tables and upload snapshot metadata to MinIO:

```bash
source .venv/bin/activate
# Preprocess markdown/rst files and split into clean paragraphs
PYTHONPATH=. python scripts/preprocess_corpus.py

# Ingest chunk text, compute all-MiniLM embeddings, and save to PostgreSQL + MinIO
PYTHONPATH=. python scripts/ingest_corpus.py
```

---

## 🧠 7. Training the Classifier Model

To train or fine-tune the classifier model on a new issue split:
1. Ensure the training data (`train.jsonl`, `val.jsonl`) is exported to `data/splits/`.
2. Follow the detailed steps in [INSTRUCTIONS.md](file:///home/usermohammad/maintainer-copilot/colab_training/INSTRUCTIONS.md) to run the training notebook on a GPU-enabled Google Colab environment.
3. Compute the SHA-256 hash of the generated model weight files.
4. Update `model_card.json` with the new hashes, hyperparameters, and F1 validation scores.
5. Export the trained model to ONNX using:
   ```bash
   PYTHONPATH=. python scripts/export_onnx.py --model_dir models/classifier/
   ```
6. Compress the models folder and deploy to the `modelserver/` microservice.

---

## 🛡️ 8. What to do when Vault is down

If Vault is offline, the FastAPI backend will immediately fail to start and logs `VaultUnavailableError: Cannot connect to Vault at http://vault:8200`.

### Recovery Steps
1. Verify if the container is running:
   ```bash
   docker compose ps vault
   ```
2. If down, restart the container:
   ```bash
   docker compose start vault
   ```
3. Check container logs for errors:
   ```bash
   docker compose logs vault
   ```
4. If Vault was fully deleted/reset, re-initialize it to seed the secrets:
   ```bash
   bash scripts/vault_init.sh
   ```
5. Restart the FastAPI backend once Vault shows healthy.

---

## ⏪ 9. Rolling Back a Bad Deployment

If a bad commit or degraded model is deployed to production:
1. Revert to the last stable release tag:
   ```bash
   git checkout v0.1.0-stable
   ```
2. Force recreate all services to use the stable build:
   ```bash
   docker compose up -d --build --force-recreate
   ```
3. Run migrations rollback if database schemas changed:
   ```bash
   # (Run standard rollback migration steps depending on revision)
   docker compose run --rm migrate alembic downgrade -1
   ```
