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