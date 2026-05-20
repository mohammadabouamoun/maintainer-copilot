import structlog
from typing import List, Optional
from app.domain.schemas import Chunk

logger = structlog.get_logger()

class RerankerService:
    def __init__(self, model: Optional[object] = None):
        """
        Initializes the RerankerService with an optional cross-encoder model.
        If model is None (PyTorch-free deployments), reranking falls back to
        sorting by the existing RRF hybrid retrieval score.
        Standard 2: Dependency Injection & Standard 3: Singletons.
        """
        self.model = model

    def rerank(self, query: str, chunks: List[Chunk], top_n: int = 5) -> List[Chunk]:
        """
        Re-sorts a list of candidate chunks.
        With a model: uses deep cross-encoder attention scoring.
        Without a model (model=None): falls back to sorting by existing RRF score.
        Returns the top_n most relevant chunks.
        """
        if not chunks:
            return []

        logger.info("Starting reranking", query=query, input_chunks=len(chunks), top_n=top_n)

        if self.model is None:
            # Fallback: sort by existing hybrid retrieval RRF score (already meaningful)
            logger.info("No cross-encoder model — using RRF score passthrough")
            reranked_chunks = sorted(chunks, key=lambda x: x.score, reverse=True)
        else:
            # Deep cross-encoder scoring via fastembed TextCrossEncoder
            documents = [chunk.content for chunk in chunks]
            ranked_results = list(self.model.rerank(query, documents))

            # Assign cross-encoder scores back to chunk objects
            for result in ranked_results:
                chunks[result.index].score = float(result.score)

            reranked_chunks = sorted(chunks, key=lambda x: x.score, reverse=True)

        final_results = reranked_chunks[:top_n]
        logger.info("Reranking complete", return_count=len(final_results))
        return final_results
