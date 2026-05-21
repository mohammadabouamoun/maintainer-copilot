# Maintainer's Copilot 🤖

Maintainer's Copilot is an AI-powered assistant designed for open-source project maintainers. It simplifies issue triage, provides semantic context retrieval (RAG) over project documentation and resolved issues, and manages a long-term memory system (episodic, semantic, and procedural) to deliver highly personalized support.

---
🔗 Colab Notebook:
https://colab.research.google.com/drive/1hGungytuDHT7wDPri7WRQlJp6MwNf6XP?usp=sharing

## 🌟 Key Features

*   **RAG Engine (Retrieval-Augmented Generation)**: Uses dense/sparse hybrid search with Reciprocal Rank Fusion (RRF) and Query Rewriting to retrieve relevant context from document chunks and issue histories.
*   **Tool-Using AI Agent**: Built on top of Groq and Llama-3.1-8b, equipped with autonomous tools:
    *   `search_knowledge_base` (RAG search)
    *   `classify_issue` (ML-based triage classification)
    *   `extract_entities` (Extract operating systems, libraries, and libraries versions)
    *   `summarize_thread` (Summarize issue comment histories)
    *   `write_memory` (Persist long-term context about the user)
*   **Streamlit Admin Control Room**:
    *   **Chat Console**: Directly test the LLM agent's capability.
    *   **Memory Inspector**: Audit, search, and delete episodic, semantic, or procedural user memories stored in the vector database.
    *   **Widget Config Dashboard**: Manage widgets, whitelisted host origins, greeting messages, primary theme colors, and active tools.
*   **React Chat Widget**: A floating chat widget embeddable on any documentation page via a single script tag. It features dynamic custom-color theme loading and strict CORS origin verification to prevent unauthorized usage.
*   **Security Redaction Layer**: Intercepts logging and OpenTelemetry tracing exports to redact sensitive variables (OpenAI API keys, DB connection strings, passwords, etc.) before writing to disk or exporting to Jaeger.

---

## 🛠️ Technology Stack

*   **Core API Framework**: FastAPI (Async-first, with refuse-to-boot lifecycle validation)
*   **Databases**: PostgreSQL + `pgvector` (Vector database), Redis (Caching & sessions)
*   **Storage**: MinIO (Object store)
*   **Secrets**: HashiCorp Vault
*   **Monitoring**: OpenTelemetry + Jaeger
*   **Admin UI**: Streamlit
*   **Widget UI**: React + Vite

---

## 🚀 Quick Start (Local Setup)

To spin up the entire Maintainer's Copilot ecosystem on your local machine, follow these steps:

### 1. Environment Configuration
Copy the template configuration file and verify your variables:
```bash
cp .env.example .env
```

### 2. Launch Infrastructure Services
Start the supporting databases, security services, and demo servers inside Docker Compose:
```bash
docker compose up -d db redis minio vault migrate widget host
```
*(This starts PostgreSQL, Redis, MinIO, Vault, the React dev server on port `3000`, and the Nginx host page on port `9000`)*.

### 3. Start Core Backends
Install dependencies and run the ModelServer and FastAPI Backend:
```bash
# Terminal 1: Run ModelServer (Inference Engine)
PYTHONPATH=. .venv/bin/python modelserver/app.py

# Terminal 2: Run FastAPI Backend
PYTHONPATH=. .venv/bin/uvicorn app.api.server:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Start the Admin Console
Start the Streamlit panel in a separate terminal:
```bash
API_URL=http://localhost:8000 .venv/bin/streamlit run chatbot/app.py --server.port 8501
```

---

## 🧪 Verification & Testing

Once all components are running, you can verify functionality using these interfaces:

### A. Admin Dashboard
*   **URL**: `http://localhost:8501`
*   **Default Credentials**:
    *   **Email**: `admin@test.com`
    *   **Password**: `password123`
*   *Use the sidebar to navigate between **Chat**, **Memory Inspector**, and **Widget Config** tabs.*

### B. Public Host Page & Widget
*   **URL**: `http://localhost:9000`
*   *Click the floating chat bubble in the bottom right corner to interact with the widget.*
*   **Try these sample queries:**
    1.  *“What is the new dtype_backend argument in pandas 2.0?”*
    2.  *“Classify this issue: When importing pandas 2.0 on python 3.12, the interpreter throws an ImportError.”*
    3.  *“Remember that I am using Ubuntu 22.04 and prefer dark mode.”* (Then ask *“What is my preferred OS?”* and check the Memory Inspector in Streamlit to verify it was saved).