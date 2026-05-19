import structlog
from typing import List
from sentence_transformers import CrossEncoder
from app.domain.schemas import Chunk

logger = structlog.get_logger()

class RerankerService:
    def __init__(self, model: CrossEncoder):
        """
        Initializes the RerankerService with an injected CrossEncoder dependency.
        Standard 2: Dependency Injection & Standard 3: Singletons.
        """
        self.model = model

    def rerank(self, query: str, chunks: List[Chunk], top_n: int = 5) -> List[Chunk]:
        """
        Re-sorts a list of candidate chunks using a deep cross-encoder model.
        Returns the top_n most relevant chunks with updated scores.
        """
        if not chunks:
            return []
            
        logger.info("Starting reranking", query=query, input_chunks=len(chunks), top_n=top_n)
        
        # Prepare pairs for the cross encoder: (query, chunk_content)
        pairs = [[query, chunk.content] for chunk in chunks]
        
        # Predict cross-attention scores
        # Note: This is synchronous CPU-heavy work.
        scores = self.model.predict(pairs)
        
        # Assign new scores and sort
        for i, chunk in enumerate(chunks):
            chunk.score = float(scores[i])
            
        # Sort descending by the new cross-encoder score
        reranked_chunks = sorted(chunks, key=lambda x: x.score, reverse=True)
        
        # Return top_n
        final_results = reranked_chunks[:top_n]
        logger.info("Reranking complete", return_count=len(final_results))
        
        return final_results
