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