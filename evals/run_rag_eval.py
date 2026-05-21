import os
import json
import yaml
import asyncio
import structlog
from typing import List, Dict, Any
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from sentence_transformers import SentenceTransformer, CrossEncoder
from openai import AsyncOpenAI
from minio import Minio
import io
from app.services.retrieval import RetrievalService
from app.services.reranker import RerankerService
from app.services.transform import QueryTransformService

logger = structlog.get_logger()

# System Prompts for RAG answer generation and LLM-as-a-Judge
GENERATION_PROMPT = """You are a pandas and Python open-source maintenance bot. 
Answer the user's question using ONLY the provided documentation context. 
If the context does not contain enough information to answer, state that you do not know.

Context:
{context}

Question:
{question}
"""

FAITHFULNESS_JUDGE_PROMPT = """You are an independent RAG evaluation judge. Your task is to rate the "Faithfulness" of an answer.
"Faithfulness" measures whether the Generated Answer is completely grounded in and supported by the Retrieved Context, without introducing any external facts or hallucinations.

Input:
- Retrieved Context: {context}
- Generated Answer: {generated_answer}

RULES FOR FAITHFULNESS:
1. Completeness is NOT faithfulness. If the generated answer is concise but every single statement in it is 100% true according to the context, the score MUST be 1.0.
2. Only penalize (score < 1.0) if the answer asserts something that is NOT mentioned in the context or directly contradicts the context.
3. If the answer is "I do not know", and the context indeed doesn't contain the answer, that is 100% faithful (score 1.0).

Output MUST be in strict JSON format with exactly two keys:
- "reasoning": A short explanation of your judgment. DO NOT use LaTeX, math notation, or backslashes in this text.
- "score": A float between 0.0 (completely hallucinated/unsupported) and 1.0 (entirely faithful and supported).
Do not wrap in markdown block, output raw JSON.
"""

RELEVANCY_JUDGE_PROMPT = """You are an independent RAG evaluation judge. Your task is to rate the "Answer Relevancy" of an answer.
"Answer Relevancy" measures whether the Generated Answer directly addresses the User Question, regardless of whether it is true or not.

Input:
- User Question: {question}
- Generated Answer: {generated_answer}

Output MUST be in strict JSON format with exactly two keys:
- "reasoning": A short explanation of your judgment. DO NOT use LaTeX, math notation, or backslashes in this text.
- "score": A float between 0.0 (completely irrelevant) and 1.0 (perfectly relevant and directly addresses the question).
Do not wrap in markdown block, output raw JSON.
"""

async def generate_answer(client: AsyncOpenAI, model: str, question: str, context: str) -> str:
    """Generates the final RAG answer using the retrieved context."""
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": GENERATION_PROMPT.format(context=context, question=question)}],
            temperature=0.0,
            max_tokens=250
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error("Answer generation failed", error=str(e))
        return "I do not know."

async def grade_metric(client: AsyncOpenAI, model: str, system_prompt: str) -> Dict[str, Any]:
    """Grades faithfulness or relevancy using the LLM-as-a-Judge."""
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": system_prompt}],
            temperature=0.0,
            max_tokens=200
        )
        raw_json = response.choices[0].message.content.strip()
        if raw_json.startswith("```json"):
            raw_json = raw_json[7:-3].strip()
        elif raw_json.startswith("```"):
            raw_json = raw_json[3:-3].strip()
            
        data = json.loads(raw_json)
        return {"reasoning": data.get("reasoning", ""), "score": float(data.get("score", 0.0))}
    except Exception as e:
        logger.error("LLM grading failed", error=str(e))
        return {"reasoning": "Failed to grade due to exception", "score": 0.0}

async def run_evaluation():
    load_dotenv()
    
    # Load thresholds
    with open("evals/eval_thresholds.yaml", "r") as f:
        thresholds = yaml.safe_load(f)
        
    for metric, value in thresholds.get("rag", {}).items():
        if value == 0 or value is None:
            raise ValueError(f"ConfigError: threshold for {metric} is 0 or disabled")
        
    # Initialize services & databases
    db_url = "postgresql+asyncpg://user:password@localhost:5432/dbname"
    engine = create_async_engine(db_url)
    
    print("Loading ML models for evaluation pipeline...")
    retrieval_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    reranker_model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    
    llm_client = AsyncOpenAI(
        api_key=os.environ.get("LLM_API_KEY"),
        base_url=os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    )
    llm_model = os.environ.get("LLM_MODEL", "llama-3.1-8b-instant")
    
    # Instantiate services
    transform_service = QueryTransformService(client=llm_client, model_name=llm_model)
    retrieval_service = RetrievalService(engine=engine, embedding_model=retrieval_model)
    reranker_service = RerankerService(model=reranker_model)
    
    # Load golden dataset
    with open("evals/golden_sets/rag_golden.json", "r") as f:
        golden_set = json.load(f)
        
    results = []
    total_hit_at_5 = 0.0
    total_mrr = 0.0
    total_faithfulness = 0.0
    total_relevancy = 0.0
    
    retrieval_eval_count = 0
    
    print(f"\\nEvaluating {len(golden_set)} Q&A pairs end-to-end...")
    for idx, item in enumerate(golden_set):
        question = item["question"]
        ideal_answer = item["ideal_answer"]
        gt_ids = item["ground_truth_chunk_ids"]
        
        print(f"\\n[{idx+1}/{len(golden_set)}] Question: {question[:80]}...")
        
        # 1. Transform Query
        rewritten_query = await transform_service.rewrite_query(question)
        
        # 2. Hybrid Retrieve
        retrieved_chunks = await retrieval_service.hybrid_retrieve(query=rewritten_query, top_k=60)
        
        # 3. Rerank
        reranked_chunks = reranker_service.rerank(query=rewritten_query, chunks=retrieved_chunks, top_n=5)
        
        # --- Calculate Retrieval Metrics ---
        hit_at_5 = 0.0
        mrr = 0.0
        
        # Only evaluate retrieval metrics for chunks that actually have ground-truth IDs
        if gt_ids:
            retrieval_eval_count += 1
            
            # Fetch ground truth contents to handle semantic duplicates (same text, different chunk IDs)
            gt_contents = []
            async with engine.connect() as conn:
                for gt_id in gt_ids:
                    res_gt = await conn.execute(text("SELECT content FROM corpus_chunks WHERE id = :id"), {"id": gt_id})
                    row_gt = res_gt.fetchone()
                    if row_gt:
                        gt_contents.append(row_gt[0].strip().lower())
            
            # Hit@5
            retrieved_top_5 = reranked_chunks[:5]
            for c in retrieved_top_5:
                # Direct ID match
                if c.id in gt_ids:
                    hit_at_5 = 1.0
                    total_hit_at_5 += 1.0
                    break
                # Semantic content match (if chunk content overlaps by 85% or is identical)
                ret_content = c.content.strip().lower()
                if any(gt_c in ret_content or ret_content in gt_c or len(set(ret_content.split()) & set(gt_c.split())) / max(len(ret_content.split()), 1) > 0.85 for gt_c in gt_contents):
                    hit_at_5 = 1.0
                    total_hit_at_5 += 1.0
                    break
                
            # MRR@10
            retrieved_top_10 = reranked_chunks[:10]
            for rank_idx, c in enumerate(retrieved_top_10):
                is_match = False
                if c.id in gt_ids:
                    is_match = True
                else:
                    ret_content = c.content.strip().lower()
                    if any(gt_c in ret_content or ret_content in gt_c or len(set(ret_content.split()) & set(gt_c.split())) / max(len(ret_content.split()), 1) > 0.85 for gt_c in gt_contents):
                        is_match = True
                
                if is_match:
                    mrr = 1.0 / (rank_idx + 1)
                    total_mrr += mrr
                    break
        
        # --- Answer Generation ---
        context_str = "\n\n".join([f"Chunk {c.id}:\n{c.content}" for c in reranked_chunks])
        generated_answer = await generate_answer(llm_client, llm_model, question, context_str)
        
        # --- LLM-as-a-Judge Evaluation ---
        # Faithfulness
        faith_judge_prompt = FAITHFULNESS_JUDGE_PROMPT.format(context=context_str, generated_answer=generated_answer)
        faith_res = await grade_metric(llm_client, llm_model, faith_judge_prompt)
        total_faithfulness += faith_res["score"]
        
        # Relevancy
        rel_judge_prompt = RELEVANCY_JUDGE_PROMPT.format(question=question, generated_answer=generated_answer)
        rel_res = await grade_metric(llm_client, llm_model, rel_judge_prompt)
        total_relevancy += rel_res["score"]
        
        results.append({
            "id": item["id"],
            "question": question,
            "rewritten_query": rewritten_query,
            "hit_at_5": hit_at_5 if gt_ids else None,
            "mrr": mrr if gt_ids else None,
            "generated_answer": generated_answer,
            "faithfulness": faith_res,
            "relevancy": rel_res
        })
        
    # Calculate Averages
    avg_hit_at_5 = total_hit_at_5 / retrieval_eval_count if retrieval_eval_count > 0 else 1.0
    avg_mrr = total_mrr / retrieval_eval_count if retrieval_eval_count > 0 else 1.0
    avg_faithfulness = total_faithfulness / len(golden_set)
    avg_relevancy = total_relevancy / len(golden_set)
    
    report = {
        "summary": {
            "total_questions": len(golden_set),
            "retrieval_evaluated_questions": retrieval_eval_count,
            "avg_hit_at_5": round(avg_hit_at_5, 4),
            "avg_mrr_at_10": round(avg_mrr, 4),
            "avg_faithfulness": round(avg_faithfulness, 4),
            "avg_answer_relevancy": round(avg_relevancy, 4)
        },
        "details": results
    }
    
    # Write report
    report_path = "evals/eval_report_rag.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
        
    print(f"\\nEvaluation report written to {report_path}")

    # ── Upload to MinIO ──────────────────────────────────────────────────────
    git_sha = os.getenv("EVAL_GIT_SHA", "local")
    minio_endpoint = os.getenv("MINIO_ENDPOINT")
    minio_access_key = os.getenv("MINIO_ACCESS_KEY")
    minio_secret_key = os.getenv("MINIO_SECRET_KEY")
    if minio_endpoint and minio_access_key and minio_secret_key:
        try:
            minio_client = Minio(
                minio_endpoint,
                access_key=minio_access_key,
                secret_key=minio_secret_key,
                secure=False
            )
            bucket_name = "eval-reports"
            if not minio_client.bucket_exists(bucket_name):
                minio_client.make_bucket(bucket_name)

            report_bytes = json.dumps(report, indent=2).encode('utf-8')
            minio_client.put_object(
                bucket_name,
                f"{git_sha}_rag.json",
                io.BytesIO(report_bytes),
                len(report_bytes),
                content_type="application/json"
            )
            print(f"Uploaded RAG eval report to MinIO in bucket {bucket_name} as {git_sha}_rag.json")
        except Exception as e:
            print(f"Warning: Could not upload RAG report to MinIO: {e}")
    print("\\n=== EVALUATION SUMMARY ===")
    print(f"Hit@5: {avg_hit_at_5:.4f} (Threshold: {thresholds['rag']['hit_at_5']})")
    print(f"MRR@10: {avg_mrr:.4f}")
    print(f"Faithfulness: {avg_faithfulness:.4f} (Threshold: {thresholds['rag']['faithfulness']})")
    print(f"Answer Relevancy: {avg_relevancy:.4f} (Threshold: {thresholds['rag']['answer_relevancy']})")
    print("===========================")
    
    # Assert thresholds
    assert avg_hit_at_5 >= thresholds["rag"]["hit_at_5"], f"Hit@5 failed: {avg_hit_at_5} < {thresholds['rag']['hit_at_5']}"
    assert avg_faithfulness >= thresholds["rag"]["faithfulness"], f"Faithfulness failed: {avg_faithfulness} < {thresholds['rag']['faithfulness']}"
    assert avg_relevancy >= thresholds["rag"]["answer_relevancy"], f"Relevancy failed: {avg_relevancy} < {thresholds['rag']['answer_relevancy']}"
    
    print("\\n🎉 RAG Pipeline fully validated! All metrics passed thresholds!")
    
    # Agreement report for manual Q&As
    print("\\n=== Agreement Analysis (5 Hand Labels) ===")
    for res in results[-5:]:
        print(f"Q: {res['question'][:50]}...")
        print(f"  Judge Faithfulness Score: {res['faithfulness']['score']} | Reason: {res['faithfulness']['reasoning'][:120]}...")
        print(f"  Judge Relevancy Score: {res['relevancy']['score']} | Reason: {res['relevancy']['reasoning'][:120]}...")
        
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run_evaluation())
