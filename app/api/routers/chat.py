import uuid
import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List

from app.config import get_settings
from app.services.auth import current_active_user, fastapi_users
current_active_user_optional = fastapi_users.current_user(active=True, optional=True)
from app.domain.exceptions import NotFoundError, PermissionDenied

logger = structlog.get_logger()

router = APIRouter()

class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    message: str
    widget_id: Optional[str] = None

class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: str

class ConversationDetailResponse(BaseModel):
    id: str
    user_id: str
    created_at: str
    messages: List[MessageResponse]

@router.post("/message")
async def chat_message(
    request: Request,
    body: ChatRequest,
    user = Depends(current_active_user_optional)
):
    """
    Sends a message to the chatbot service and streams the token-by-token response back.
    Includes dynamic tool resolution and persistence.
    """
    conversation_id = body.conversation_id or str(uuid.uuid4())
    settings = get_settings()
    db_engine = request.app.state.db_engine

    if not user:
        if not body.widget_id:
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Unauthorized")
        
        # Verify widget and origin
        from sqlalchemy.ext.asyncio import AsyncSession
        from sqlalchemy import select
        from app.repositories.models import Widget
        from fastapi import HTTPException
        
        try:
            widget_uuid = uuid.UUID(body.widget_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid widget ID format")
            
        async with AsyncSession(db_engine) as session:
            stmt = select(Widget).where(Widget.widget_id == widget_uuid)
            res = await session.execute(stmt)
            widget = res.scalar_one_or_none()
            if not widget:
                raise HTTPException(status_code=404, detail="Widget not found")
            
            # Simple CORS/Origin verification
            origin = request.headers.get("origin") or ""
            referer = request.headers.get("referer") or ""
            
            is_allowed = False
            for allowed in widget.allowed_origins:
                if allowed in origin or allowed in referer:
                    is_allowed = True
                    break
            
            if not is_allowed and widget.allowed_origins:
                raise HTTPException(status_code=403, detail="Origin not allowed")
                
            user_id = widget.created_by
            user_email = "anonymous-widget-user"
    else:
        user_id = user.id
        user_email = user.email

    logger.info("Chat message received", conversation_id=conversation_id, user_email=user_email)

    openai_client = request.app.state.openai_client
    minio_client = request.app.state.minio_client
    retrieval_model = request.app.state.retrieval_model
    reranker_model = request.app.state.reranker_model

    # 1. Instantiate RAGService dependencies (Dependency Injection)
    from app.services.transform import QueryTransformService
    from app.services.retrieval import RetrievalService
    from app.services.reranker import RerankerService
    from app.services.rag_service import RAGService

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
    rag_service = RAGService(
        transform_service=transform_service,
        retrieval_service=retrieval_service,
        reranker_service=reranker_service,
        openai_client=openai_client,
        minio_client=minio_client,
        settings=settings
    )

    # 2. Instantiate ChatbotService
    from app.services.chatbot import ChatbotService
    chatbot_service = ChatbotService(
        openai_client=openai_client,
        db_engine=db_engine,
        minio_client=minio_client,
        rag_service=rag_service,
        retrieval_model=retrieval_model,
        settings=settings
    )

    async def event_generator():
        try:
            # Yield conversation ID first so the client can map dynamic new sessions
            yield f"CONVERSATION_ID:{conversation_id}\n"
            
            async for token in chatbot_service.chat(
                conversation_id=conversation_id,
                user_message=body.message,
                user_id=user_id
            ):
                yield token
        except Exception as e:
            logger.error("Chat streaming failed", error=str(e))
            yield f"\n[Error: {str(e)}]"

    return StreamingResponse(event_generator(), media_type="text/plain")



@router.get("/conversations/{id}", response_model=ConversationDetailResponse)
async def get_conversation(
    id: str,
    request: Request,
    user = Depends(current_active_user)
):
    """
    Fetches the details and full message history of a specific conversation.
    Validates user ownership boundaries.
    """
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    from app.repositories.models import Conversation, Message

    try:
        conv_uuid = uuid.UUID(id)
    except ValueError:
        raise NotFoundError(f"Invalid conversation ID format: {id}")

    db_engine = request.app.state.db_engine

    async with AsyncSession(db_engine) as session:
        stmt = select(Conversation).where(Conversation.id == conv_uuid)
        res = await session.execute(stmt)
        conversation = res.scalar_one_or_none()

        if not conversation:
            raise NotFoundError(f"Conversation {id} not found.")

        if conversation.user_id != user.id:
            raise PermissionDenied("You do not have access to this conversation.")

        msg_stmt = select(Message).where(Message.conversation_id == conv_uuid).order_by(Message.created_at.asc())
        msg_res = await session.execute(msg_stmt)
        messages = msg_res.scalars().all()

        return ConversationDetailResponse(
            id=str(conversation.id),
            user_id=str(conversation.user_id),
            created_at=conversation.created_at.isoformat(),
            messages=[
                MessageResponse(
                    id=str(m.id),
                    role=m.role,
                    content=m.content,
                    created_at=m.created_at.isoformat()
                )
                for m in messages
            ]
        )
