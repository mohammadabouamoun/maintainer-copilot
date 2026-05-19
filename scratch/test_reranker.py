import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sentence_transformers import SentenceTransformer, CrossEncoder
from app.services.retrieval import RetrievalService
from app.services.reranker import RerankerService

async def main():
    db_url = "postgresql+asyncpg://user:password@localhost:5432/dbname"
    engine = create_async_engine(db_url)
    
    print("Loading models (this might take a few seconds)...")
    # 1. Load retrieval embedding model
    retrieval_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    # 2. Load reranking cross-encoder model
    reranker_model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    
    retrieval_service = RetrievalService(engine=engine, embedding_model=retrieval_model)
    reranker_service = RerankerService(model=reranker_model)
    
    # Intentionally tricky query: "How to drop missing values but only if the whole row is NA"
    # Naive keyword/vector search often just brings up general dropna documentation.
    # Cross-encoder should recognize the "whole row is NA" specifically means how='all'.
    query = "How to drop missing values but only if the whole row is NA"
    print(f"\\nQuerying: '{query}'")
    
    # 1. Fetch top 20 broad candidates via Hybrid RRF
    print("\\n--- Running Hybrid Retrieval (Top 20 candidates) ---")
    hybrid_results = await retrieval_service.hybrid_retrieve(query=query, top_k=20)
    
    print("\\nHybrid Top 3:")
    for i, res in enumerate(hybrid_results[:3]):
        snippet = res.content[:150].replace('\\n', ' ') + "..."
        print(f"{i+1}. [Score: {res.score:.4f}] {res.source_id} - {snippet}")
        
    # Find where the actual best answer (using how='all') is ranked in hybrid
    best_chunk_hybrid_rank = -1
    for i, res in enumerate(hybrid_results):
        if "how" in res.content and "all" in res.content and "dropna" in res.content:
            best_chunk_hybrid_rank = i + 1
            break
            
    print(f"\\n-> Best contextual chunk (mentioning how='all') was ranked #{best_chunk_hybrid_rank} by Hybrid Search.")
    
    # 2. Rerank down to top 5
    print("\\n--- Running Cross-Encoder Reranker (Filtering to Top 5) ---")
    reranked_results = reranker_service.rerank(query=query, chunks=hybrid_results, top_n=5)
    
    print("\\nReranked Top 3:")
    for i, res in enumerate(reranked_results[:3]):
        snippet = res.content[:150].replace('\\n', ' ') + "..."
        print(f"{i+1}. [Score: {res.score:.4f}] {res.source_id} - {snippet}")
        
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
