from fastapi import APIRouter, Depends, Request
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from opentelemetry import trace

from app.config import get_settings
from app.domain.schemas import Chunk
from app.services.auth import current_active_user
from app.services.transform import QueryTransformService
from app.services.retrieval import RetrievalService
from app.services.reranker import RerankerService
from app.services.rag_service import RAGService

router = APIRouter()

class RAGQueryRequest(BaseModel):
    question: str
    conversation_id: Optional[str] = None
    metadata_filter: Optional[Dict[str, Any]] = None

class RAGQueryResponse(BaseModel):
    answer: str
    chunks: List[Chunk]
    trace_id: str

def get_active_trace_id() -> str:
    span = trace.get_current_span()
    span_context = span.get_span_context() if span else None
    if span_context and span_context.is_valid:
        return trace.format_trace_id(span_context.trace_id)
    return "unknown"

@router.post("/query", response_model=RAGQueryResponse)
async def query_rag(
    request: Request,
    body: RAGQueryRequest,
    user=Depends(current_active_user)
):
    settings = get_settings()
    
    # 1. Retrieve singletons from request.app.state
    db_engine = request.app.state.db_engine
    retrieval_model = request.app.state.retrieval_model
    reranker_model = request.app.state.reranker_model
    openai_client = request.app.state.openai_client
    minio_client = request.app.state.minio_client

    # 2. Instantiate intermediate services (Standard 2: Dependency Injection)
    transform_service = QueryTransformService(
        client=openai_client,
        model_name=settings.llm_model
    )
    retrieval_service = RetrievalService(
        engine=db_engine,
        embedding_model=retrieval_model
    )
    reranker_service = RerankerService(
        model=reranker_model
    )

    # 3. Instantiate orchestrator
    rag_service = RAGService(
        transform_service=transform_service,
        retrieval_service=retrieval_service,
        reranker_service=reranker_service,
        openai_client=openai_client,
        minio_client=minio_client,
        settings=settings
    )

    # 4. Orchestrate
    answer, chunks = await rag_service.query(
        question=body.question,
        conversation_id=body.conversation_id,
        metadata_filter=body.metadata_filter
    )

    # 5. Extract active OTel Trace ID
    trace_id = get_active_trace_id()

    return RAGQueryResponse(
        answer=answer,
        chunks=chunks,
        trace_id=trace_id
    )
