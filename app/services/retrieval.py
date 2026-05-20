import structlog
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy import text
from fastembed import TextEmbedding
from app.domain.schemas import Chunk

logger = structlog.get_logger()

class RetrievalService:
    def __init__(self, engine: AsyncEngine, embedding_model: TextEmbedding):
        """
        Initializes the RetrievalService with injected dependencies to adhere to Standard 2.
        """
        self.engine = engine
        self.model = embedding_model
        
    async def _dense_search(self, query: str, top_k: int) -> dict:
        """Performs semantic vector search using pgvector cosine distance."""
        # fastembed.embed() returns a generator; take the first element
        query_vector = list(self.model.embed([query]))[0].tolist()
        
        stmt = text("""
            SELECT id, source_type, source_id, chunk_index, content, metadata,
                   embedding <=> cast(:vector as vector) AS distance
            FROM corpus_chunks
            ORDER BY distance ASC
            LIMIT :top_k
        """)
        
        results = {}
        async with self.engine.connect() as conn:
            rows = await conn.execute(stmt, {"vector": str(query_vector), "top_k": top_k})
            for i, row in enumerate(rows.mappings()):
                results[str(row["id"])] = {
                    "data": dict(row),
                    "rank": i + 1
                }
        return results

    async def _sparse_search(self, query: str, top_k: int) -> dict:
        """Performs full-text keyword search using Postgres tsvector dynamically with logical OR to maximize recall."""
        import re
        # Clean the query, extract alphanumeric words, and join them with logical OR '|'
        words = re.findall(r'\w+', query)
        if not words:
            return {}
        or_query = " | ".join(words)
        
        stmt = text("""
            WITH search_query AS (
                SELECT to_tsquery('english', :or_query) AS q
            )
            SELECT id, source_type, source_id, chunk_index, content, metadata,
                   ts_rank(to_tsvector('english', content), q) AS rank_score
            FROM corpus_chunks, search_query
            WHERE to_tsvector('english', content) @@ q
            ORDER BY rank_score DESC
            LIMIT :top_k
        """)
        
        results = {}
        async with self.engine.connect() as conn:
            rows = await conn.execute(stmt, {"or_query": or_query, "top_k": top_k})
            for i, row in enumerate(rows.mappings()):
                results[str(row["id"])] = {
                    "data": dict(row),
                    "rank": i + 1
                }
        return results

    async def hybrid_retrieve(self, query: str, top_k: int = 20, metadata_filter: Optional[dict] = None) -> List[Chunk]:
        """
        Fuses dense and sparse search results using Reciprocal Rank Fusion (RRF).
        RRF Score = 1 / (k + rank), where k is typically 60.
        """
        logger.info("Starting hybrid retrieval", query=query, top_k=top_k)
        
        # Fetch top 50 from both sources to ensure good fusion candidates
        fetch_k = max(top_k * 2, 50)
        
        dense_res = await self._dense_search(query, top_k=fetch_k)
        sparse_res = await self._sparse_search(query, top_k=fetch_k)
        
        rrf_k = 60
        fused_scores = {}
        chunk_data = {}
        
        # Process Dense Ranks
        for chunk_id, info in dense_res.items():
            fused_scores[chunk_id] = 1.0 / (rrf_k + info["rank"])
            chunk_data[chunk_id] = info["data"]
            
        # Process Sparse Ranks
        for chunk_id, info in sparse_res.items():
            if chunk_id not in fused_scores:
                fused_scores[chunk_id] = 0.0
                chunk_data[chunk_id] = info["data"]
            fused_scores[chunk_id] += 1.0 / (rrf_k + info["rank"])
            
        # Sort aggressively by the fused RRF score
        sorted_chunks = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
        
        # Take the absolute top_k results
        final_results = []
        for chunk_id, score in sorted_chunks[:top_k]:
            data = chunk_data[chunk_id]
            final_results.append(
                Chunk(
                    id=str(data["id"]),
                    source_type=data["source_type"],
                    source_id=data["source_id"],
                    chunk_index=data["chunk_index"],
                    content=data["content"],
                    metadata=data["metadata"],
                    score=round(score, 4)
                )
            )
            
        logger.info("Hybrid retrieval complete", return_count=len(final_results))
        return final_results
