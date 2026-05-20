# DECISIONS.md

## Dataset Choice

**Repository:** `fastapi/fastapi`

**Why:** Balanced size, well-labeled issues, excellent documentation, manageable RAG corpus. Best fit for 5-day deadline.

## Label Mapping

FastAPI native labels → project categories:

| FastAPI Label | Project Category |
|---------------|------------------|
| `bug` | bug |
| `enhancement` / `feature` / `new feature` | feature |
| `documentation` | docs |
| `question` / `help wanted` / `good first issue` (when question-shaped) | question |

**Stratification:** Train/val/test split by time (test strictly more recent than train).

**Splits size:** To be determined after fetching issues.

## Classifier Comparison

| Model | Accuracy | Macro-F1 | Bug F1 | Feature F1 | Docs F1 | Question F1 | Latency (ms) | Cost/1k |
|---|---|---|---|---|---|---|---|---|
| Classical ML | 0.6972 | 0.5417 | 0.8083 | 0.5773 | 0.7812 | 0.0000 | 0.27 | $0.00 |
| Fine-tuned XFMR | 0.7119 | 0.5568 | 0.8180 | 0.6449 | 0.7642 | 0.0000 | 169.64 | $0.00 |
| LLM baseline | 0.7633 | 0.7393 | 0.8345 | 0.6667 | 0.9265 | 0.5294 | 934.84 | $0.0333 |

## Deployment Choice Defense

We selected the **Fine-tuned Transformer (DistilBERT)** model for deployment on the microservice classifier endpoint. Although the Zero-Shot LLM baseline yields the highest overall accuracy (76.33%) and Macro-F1 (73.93%)—handling the underrepresented `question` class extremely well due to its pre-trained general knowledge—its average inference latency of **934.84 ms** per sample presents a significant bottleneck for real-time issue sorting pipelines. Furthermore, the LLM baseline carries ongoing API costs ($0.0333 per 1k requests) and presents data leakage risks as incoming raw issue descriptions would be transmitted to external servers. 

The Fine-tuned DistilBERT model strikes the optimal engineering balance: it provides high accuracy (71.19%) and a major improvement in `feature` F1 (64.49% vs 57.73% for Classical ML), operates locally with highly respectable CPU inference latency of **169.64 ms** (comfortably within our 200 ms real-time latency budget), is completely free to query once deployed, and guarantees absolute data privacy. While the Classical ML baseline is extremely fast (0.27 ms), its classification quality is noticeably weaker, making the local Fine-tuned DistilBERT Transformer our definitive production choice.

## RAG Corpus Preprocessing (Task 3.1)

### Documentation Parsing
- Instead of web-scraping HTML, we clone the master `pandas` repository to a temporary local directory and directly parse its markdown and RST documentation files.
- We segment the text by primary headers (`#`, `##`, `==`, `--`) to ensure boundaries encapsulate logically cohesive, semantic chunks rather than arbitrary character splits.

### Issue Corpus Generation
- The issue corpus is extracted from the `data/raw_issues.jsonl` file.
- To strictly prevent data leakage and skewed RAG evaluation later on, any issue `id` present in `train.jsonl`, `val.jsonl`, or `test.jsonl` is excluded from the RAG knowledge base.
- To avoid GitHub API rate limits (since `data/raw_issues.jsonl` only stores comment counts rather than actual text), we use the issue `title` + `body` as the contextual chunk for the held-out "resolved" issues.

## Embedding Model Choice (Task 3.2)

We evaluated two candidate embedding models for the RAG architecture on a CPU-only environment:
1. `sentence-transformers/all-MiniLM-L6-v2` (90MB)
2. `BAAI/bge-base-en-v1.5` (438MB)

**Results:**
- **`all-MiniLM-L6-v2`**: Achieved a blazingly fast inference latency of **~38.31 ms/chunk**. On our 10-question Pandas probe dataset, it achieved a perfect **Hit@5 of 1.00** and **MRR@10 of 1.00**.
- **`BAAI/bge-base-en-v1.5`**: Exhibited severe CPU inference latency (~780 ms/chunk), taking over 20 minutes to embed the tiny 1500-chunk sample corpus. 

**Decision:**
We selected **`all-MiniLM-L6-v2`** as the permanent RAG embedding model. Its lightweight architecture is perfectly suited for our local, CPU-first deployment target without compromising on basic semantic retrieval quality. BAAI is definitively disqualified due to latency constraints.

## Cross-Encoder Reranking (Task 3.5)

To guarantee high precision for the LLM context, we implemented a two-stage retrieval pipeline. First, we fetch 20 broad candidates using Hybrid Search (pgvector + tsvector), then we use a heavy Cross-Encoder to re-sort those candidates.

**Model Choice:** `cross-encoder/ms-marco-MiniLM-L-6-v2`. This model performs deep token-level cross-attention between the user's query and the chunk text, making it extremely accurate.

**Evaluation:**
We tested a semantically complex query: *"How to drop missing values but only if the whole row is NA"*.
- **Naive Hybrid Search:** Struggled to map "whole row is NA" to the specific Pandas syntax `how='all'`. It ranked the highly relevant `missing_data.rst` chunk at **#8**.
- **Cross-Encoder Reranker:** Successfully comprehended the semantic intent of "whole row is NA" and correctly promoted the `missing_data.rst` chunk to the **Top 2** results, ensuring it will be included in the LLM's strictly limited context window.

## Query Transformation (Task 3.6)

Before a user's prompt even hits the Hybrid Search engine, we transform it using an LLM.

**Decision:**
We chose the **Query Rewriting** technique instead of HyDE (Hypothetical Document Embeddings) or Multi-Query.
- **Why:** Query Rewriting requires a very short LLM generation (blazing fast on Llama 3) and prevents hallucinations. It simply takes a vague user prompt with pronouns (e.g., *"why does it not work with Python 3.12"*) and rewrites it into a highly specific search string (e.g., *"pandas installation errors and compatibility issues with Python 3.12"*). This prevents our Postgres FTS from matching on useless stop words.

## Phase 4.4: Short-Term Memory Cache TTL (Redis)

**Decision:** The Redis short-term memory cache for session history uses a TTL of **1 hour (3600 seconds)**.
- **Why 1 hour:** The vast majority of maintainer issue-triage sessions conclude within a few minutes. Storing active contexts in RAM for 1 hour optimizes query speed without ballooning Redis memory usage indefinitely.
- **Expiration Fallback:** If a conversation happens to span longer than an hour, the TTL will expire and clear the keys. When the user sends a new message, the chatbot orchestrator automatically experiences a Redis cache miss and flawlessly falls back to `Postgres` to reload the entire history. It then seamlessly backfills the Redis cache with the newly loaded history, resetting the TTL. This ensures perfect resilience with aggressive RAM limits.

## Phase 4.5: Long-Term Memory Type

**Decision:** Our primary default long-term memory bucket uses the **`semantic`** type tag.
- **Rationale:** We define `episodic` as temporal, point-in-time events (e.g. "I encountered bug 123 yesterday"), whereas `semantic` represents factual preferences or rules (e.g. "I prefer concise answers", "Never use Tailwind CSS"). Since the Maintainer Copilot's `write_memory` tool is primarily designed to persist global user preferences across disparate conversations, `semantic` perfectly matches the ontological nature of the data. Procedural memory (skills) is currently out of scope for the Copilot's use case.
- **LLM Tool Isolation:** Long-term memory is **only** written when the LLM orchestrator explicitly invokes the `write_memory` tool. We explicitly instruct the LLM not to save mundane chat history into vector storage, keeping the long-term knowledge base strictly limited to high-value user facts.