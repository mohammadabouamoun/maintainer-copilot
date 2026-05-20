import os
import io
import json
import time
import uuid
import structlog
from typing import List, Tuple, Optional
from openai import AsyncOpenAI
from minio import Minio

from app.config import Settings
from app.domain.schemas import Chunk
from app.services.transform import QueryTransformService
from app.services.retrieval import RetrievalService
from app.services.reranker import RerankerService
from app.infra.tracing import trace_span_ctx

logger = structlog.get_logger()

class RAGService:
    def __init__(
        self,
        transform_service: QueryTransformService,
        retrieval_service: RetrievalService,
        reranker_service: RerankerService,
        openai_client: AsyncOpenAI,
        minio_client: Minio,
        settings: Settings
    ):
        """
        Initializes the RAGService with injected dependencies (Standard 2: Dependency Injection).
        """
        self.transform_service = transform_service
        self.retrieval_service = retrieval_service
        self.reranker_service = reranker_service
        self.openai_client = openai_client
        self.minio_client = minio_client
        self.settings = settings
        self._prompt_template = self._load_prompt()

    def _load_prompt(self) -> str:
        prompt_path = os.path.join(os.getcwd(), "prompts", "rag_answer.txt")
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            logger.error("Prompt file not found", path=prompt_path)
            return "Answer the user's question using ONLY the provided documentation context.\nContext:\n{context}\nQuestion:\n{question}"

    async def query(
        self,
        question: str,
        conversation_id: Optional[str] = None,
        metadata_filter: Optional[dict] = None
    ) -> Tuple[str, List[Chunk]]:
        """
        Orchestrates the advanced RAG pipeline:
        transform query -> hybrid retrieve -> rerank -> generate answer -> save snapshot.
        Wrapped entirely in 'rag_query' span with individual child spans (Standard 7 & 1.5).
        """
        logger.info("Starting RAG query orchestration", question=question, conversation_id=conversation_id)

        # Ensure valid conversation_id
        resolved_conversation_id = conversation_id or str(uuid.uuid4())

        with trace_span_ctx("rag_query") as parent_span:
            parent_span.set_attribute("rag.question", question)
            parent_span.set_attribute("rag.conversation_id", resolved_conversation_id)

            # Step 1: Transform Query
            with trace_span_ctx("query_transform") as child_span:
                rewritten_query = await self.transform_service.rewrite_query(question)
                child_span.set_attribute("rag.rewritten_query", rewritten_query)

            # Step 2: Hybrid Retrieve
            with trace_span_ctx("hybrid_retrieve") as child_span:
                retrieved_chunks = await self.retrieval_service.hybrid_retrieve(
                    query=rewritten_query,
                    top_k=60,
                    metadata_filter=metadata_filter
                )
                child_span.set_attribute("rag.retrieved_count", len(retrieved_chunks))

            # Step 3: Rerank Chunks
            with trace_span_ctx("rerank") as child_span:
                reranked_chunks = self.reranker_service.rerank(
                    query=rewritten_query,
                    chunks=retrieved_chunks,
                    top_n=5
                )
                child_span.set_attribute("rag.reranked_count", len(reranked_chunks))

            # Step 4: Generate Answer
            with trace_span_ctx("generate_answer") as child_span:
                context_str = "\n\n".join([f"Chunk {c.id}:\n{c.content}" for c in reranked_chunks])
                formatted_prompt = self._prompt_template.format(context=context_str, question=question)

                try:
                    response = await self.openai_client.chat.completions.create(
                        model=self.settings.llm_model,
                        messages=[{"role": "user", "content": formatted_prompt}],
                        temperature=0.0,
                        max_tokens=250
                    )
                    answer = response.choices[0].message.content.strip()
                except Exception as e:
                    logger.error("LLM generation failed, returning fallback", error=str(e))
                    answer = "I do not know."
                    child_span.record_exception(e)

                child_span.set_attribute("rag.answer_length", len(answer))

            # Step 5: Save Snapshot to MinIO
            with trace_span_ctx("save_snapshot") as child_span:
                timestamp = int(time.time())
                object_name = f"{resolved_conversation_id}/{timestamp}.json"
                
                # Serialize top chunks
                serialized_chunks = [chunk.model_dump() for chunk in reranked_chunks]
                json_data = json.dumps(serialized_chunks, indent=2)
                data_bytes = json_data.encode("utf-8")

                try:
                    self.minio_client.put_object(
                        bucket_name="chunks",
                        object_name=object_name,
                        data=io.BytesIO(data_bytes),
                        length=len(data_bytes),
                        content_type="application/json"
                    )
                    logger.info("Snapshot uploaded to MinIO", bucket="chunks", object=object_name)
                    child_span.set_attribute("minio.bucket", "chunks")
                    child_span.set_attribute("minio.object", object_name)
                except Exception as e:
                    logger.error("Failed to upload snapshot to MinIO", error=str(e))
                    child_span.record_exception(e)

            return answer, reranked_chunks
