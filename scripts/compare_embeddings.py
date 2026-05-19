import json
import time
import numpy as np
from sentence_transformers import SentenceTransformer
import structlog

logger = structlog.get_logger()

# 1. Define the 10 manual probe questions for Pandas
PROBE_QUESTIONS = [
    {
        "query": "How do I group by multiple columns and calculate the mean?",
        "expected_keywords": ["groupby", "mean"]
    },
    {
        "query": "Why does merging two DataFrames result in NaN values?",
        "expected_keywords": ["merge", "join", "nan", "missing"]
    },
    {
        "query": "What is the difference between loc and iloc for slicing?",
        "expected_keywords": ["loc", "iloc", "slice", "indexing"]
    },
    {
        "query": "Memory usage is too high when reading a large CSV file.",
        "expected_keywords": ["read_csv", "memory", "chunksize", "dtype"]
    },
    {
        "query": "How to handle missing data or fillna in a Series?",
        "expected_keywords": ["fillna", "missing", "nan", "dropna"]
    },
    {
        "query": "Can I convert a column of strings to datetime objects?",
        "expected_keywords": ["to_datetime", "datetime", "parse"]
    },
    {
        "query": "How to pivot a DataFrame or use pivot_table?",
        "expected_keywords": ["pivot", "pivot_table", "reshape"]
    },
    {
        "query": "Applying a custom function to every row in a DataFrame",
        "expected_keywords": ["apply", "lambda", "axis"]
    },
    {
        "query": "How do I rename columns in a pandas DataFrame?",
        "expected_keywords": ["rename", "columns"]
    },
    {
        "query": "Concatenate or append multiple DataFrames together vertically",
        "expected_keywords": ["concat", "append"]
    }
]

def load_corpus_sample(max_docs=1000, max_issues=500):
    """Loads a sample of chunks from the corpus."""
    corpus = []
    
    # Load docs
    try:
        with open("data/corpus/docs.jsonl", "r") as f:
            for i, line in enumerate(f):
                if i >= max_docs: break
                data = json.loads(line)
                corpus.append(f"Title: {data['title']}\n{data['text']}")
    except FileNotFoundError:
        logger.warning("docs.jsonl not found.")

    # Load issues
    try:
        with open("data/corpus/resolved_issues.jsonl", "r") as f:
            for i, line in enumerate(f):
                if i >= max_issues: break
                data = json.loads(line)
                corpus.append(data['text'])
    except FileNotFoundError:
        logger.warning("resolved_issues.jsonl not found.")
        
    return corpus

def is_hit(chunk_text, expected_keywords):
    """Naive hit detection: check if expected keywords are in the retrieved chunk."""
    chunk_lower = chunk_text.lower()
    # If at least one expected keyword is present, we consider it a potential hit for the evaluation
    # This is a proxy for human relevance judging
    return any(kw in chunk_lower for kw in expected_keywords)

def evaluate_model(model_name, corpus):
    logger.info(f"Evaluating {model_name}")
    start_load = time.time()
    model = SentenceTransformer(model_name)
    logger.info("Model loaded", time_seconds=round(time.time() - start_load, 2))

    start_embed = time.time()
    # Embed the corpus
    corpus_embeddings = model.encode(corpus, convert_to_numpy=True, show_progress_bar=True)
    embed_time = time.time() - start_embed
    logger.info("Corpus embedded", time_seconds=round(embed_time, 2), ms_per_chunk=round(embed_time/len(corpus)*1000, 2))

    # Evaluate against probes
    hits_at_5 = 0
    mrr_at_10 = 0.0

    for probe in PROBE_QUESTIONS:
        query_emb = model.encode([probe["query"]], convert_to_numpy=True)
        
        # Cosine similarity (assuming normalized embeddings, but let's do full cosine just in case)
        # SentenceTransformers generally returns normalized vectors, so dot product is cosine sim
        scores = np.dot(corpus_embeddings, query_emb.T).flatten()
        norms = np.linalg.norm(corpus_embeddings, axis=1) * np.linalg.norm(query_emb)
        cosine_sims = scores / np.maximum(norms, 1e-9)
        
        # Get top 10 indices
        top_10_idx = np.argsort(cosine_sims)[::-1][:10]
        
        hit_found_at_5 = False
        hit_rank = None
        
        for rank, idx in enumerate(top_10_idx):
            chunk = corpus[idx]
            if is_hit(chunk, probe["expected_keywords"]):
                if rank < 5:
                    hit_found_at_5 = True
                if hit_rank is None:
                    hit_rank = rank + 1
                    break # Stop at first relevant hit for MRR
                    
        if hit_found_at_5:
            hits_at_5 += 1
        if hit_rank is not None:
            mrr_at_10 += 1.0 / hit_rank
            
    hit_at_5_score = hits_at_5 / len(PROBE_QUESTIONS)
    mrr_at_10_score = mrr_at_10 / len(PROBE_QUESTIONS)
    
    logger.info("Evaluation complete", hit_at_5=round(hit_at_5_score, 2), mrr_at_10=round(mrr_at_10_score, 2))
    
    return {
        "model": model_name,
        "embed_time_ms_per_chunk": embed_time / len(corpus) * 1000,
        "hit_at_5": hit_at_5_score,
        "mrr_at_10": mrr_at_10_score
    }

def main():
    corpus = load_corpus_sample()
    if not corpus:
        logger.error("No corpus loaded. Please run preprocess_corpus.py first.")
        return
        
    logger.info("Loaded chunks for evaluation", count=len(corpus))
    
    models_to_test = [
        "sentence-transformers/all-MiniLM-L6-v2",
        "BAAI/bge-base-en-v1.5"
    ]
    
    results = []
    for m in models_to_test:
        results.append(evaluate_model(m, corpus))
        
    logger.info("Final Comparison")
    for r in results:
        logger.info("Model Result", model=r['model'], speed_ms_chunk=round(r['embed_time_ms_per_chunk'], 2), hit_at_5=round(r['hit_at_5'], 2), mrr_at_10=round(r['mrr_at_10'], 2))

if __name__ == "__main__":
    main()
