Project 7 - Mohammad Abouamoun
Repo: https://github.com/mohammadabouamoun/maintainer-copilot
Tag: v0.1.0-week7
Dataset: fastapi/fastapi issues, [2627 train / 464 val / 545 test]

Classification — Classical: F1=0.54 | Fine-tuned: F1=0.56 | LLM: F1=0.74
Deployment choice: Fine-tuned DistilBERT - because it delivers low local CPU latency (169.6ms) and high F1 score with absolute data privacy and zero API costs.
Embedding model: all-MiniLM-L6-v2 - chosen because it achieves blazing CPU encoding speed (38ms) and perfect retrieval scores under tight memory constraints.
RAG — hit@5=1.00 | MRR@10=1.00 | Faithfulness=0.96 | Answer relevancy=0.95
Long-term memory type: semantic
Tracing backend: Jaeger - chosen because it provides high-performance OpenTelemetry visual tracing of latency, tokens, and errors out-of-the-box.
Widget bundle size: 45 KB (gzipped)
LLM: llama-3.1-8b-instant (Groq)
README contains: ARCH.md ✓ | DECISIONS.md ✓ | RUNBOOK.md ✓ | EVALS.md ✓ | SECURITY.md ✓
