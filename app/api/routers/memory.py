import uuid
import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from typing import List

from app.services.auth import current_active_user
from app.repositories.models import LongTermMemory
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = structlog.get_logger()
router = APIRouter()

class MemoryResponse(BaseModel):
    id: str
    user_id: str
    content: str
    memory_type: str
    created_at: str

@router.get("", response_model=List[MemoryResponse])
async def list_memories(
    request: Request,
    user=Depends(current_active_user)
):
    """
    List all long-term semantic memories stored for the authenticated user.
    """
    logger.info("Listing memories", user_id=str(user.id))
    db_engine = request.app.state.db_engine
    
    async with AsyncSession(db_engine) as session:
        stmt = select(LongTermMemory).where(LongTermMemory.user_id == user.id).order_by(LongTermMemory.created_at.desc())
        res = await session.execute(stmt)
        memories = res.scalars().all()
        
    return [
        {
            "id": str(m.id),
            "user_id": str(m.user_id),
            "content": m.content,
            "memory_type": m.memory_type,
            "created_at": m.created_at.isoformat()
        }
        for m in memories
    ]

@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str,
    request: Request,
    user=Depends(current_active_user)
):
    """
    Delete a specific semantic memory for the authenticated user.
    """
    logger.info("Deleting memory", memory_id=memory_id, user_id=str(user.id))
    db_engine = request.app.state.db_engine
    
    async with AsyncSession(db_engine) as session:
        async with session.begin():
            stmt = select(LongTermMemory).where(
                LongTermMemory.id == uuid.UUID(memory_id),
                LongTermMemory.user_id == user.id
            )
            res = await session.execute(stmt)
            mem = res.scalar_one_or_none()
            if mem:
                await session.delete(mem)
                
    return {"status": "deleted"}
