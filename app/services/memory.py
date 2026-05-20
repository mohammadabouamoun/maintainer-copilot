import uuid
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastembed import TextEmbedding
from sqlalchemy.ext.asyncio import AsyncEngine

from app.infra.redaction import redact
from app.infra.redis_client import get_redis_client
from app.repositories.models import Message, LongTermMemory, AuditLog

async def get_conversation_history(conversation_id: str) -> list[Message]:
    """Retrieves conversation history from Redis short-term cache."""
    client = get_redis_client()
    key = f"conversations:{conversation_id}"
    raw_messages = await client.lrange(key, 0, -1)
    if not raw_messages:
        return []
    
    messages = []
    for raw in raw_messages:
        data = json.loads(raw)
        msg = Message(
            role=data["role"],
            content=data["content"]
        )
        messages.append(msg)
    return messages

async def append_message(conversation_id: str, message: Message, ttl_seconds: int = 3600):
    """Appends a message to Redis cache with a TTL (default 1 hour)."""
    client = get_redis_client()
    key = f"conversations:{conversation_id}"
    data = json.dumps({"role": message.role, "content": message.content})
    await client.rpush(key, data)
    # Refresh TTL on each append
    await client.expire(key, ttl_seconds)

async def write_long_term(db_engine: AsyncEngine, retrieval_model: TextEmbedding, user_id: uuid.UUID, content: str, memory_type: str, actor_id: uuid.UUID) -> dict:
    """
    Writes a fact to long-term memory.
    Strictly filters the content through our security Redaction Layer prior to any database write.
    """
    # 3.8 Redaction Gate: Scrub keys and sensitive PII first
    content = redact(content)
    
    embedding = list(retrieval_model.embed([content]))[0].tolist()
    # Pad to 768 to match database schema (all-MiniLM is 384)
    if len(embedding) < 768:
        embedding.extend([0.0] * (768 - len(embedding)))

    async with AsyncSession(db_engine) as session:
        async with session.begin():
            mem = LongTermMemory(
                user_id=user_id,
                memory_type=memory_type,
                content=content,
                embedding=embedding
            )
            session.add(mem)
            await session.flush()
            
            audit = AuditLog(
                actor_id=actor_id,
                action="memory_write",
                target=str(mem.id)
            )
            session.add(audit)

    return {
        "status": "stored",
        "user_id": str(user_id),
        "content": content,
        "memory_type": memory_type,
        "actor_id": str(actor_id)
    }

async def recall_relevant(db_engine: AsyncEngine, retrieval_model: TextEmbedding, user_id: uuid.UUID, query: str, top_k: int = 5) -> list[dict]:
    """
    Retrieves semantic matches from long-term memory.
    Scrubs queries to avoid leakage of search context.
    """
    query = redact(query)
    
    embedding = list(retrieval_model.embed([query]))[0].tolist()
    # Pad to 768 to match database schema
    if len(embedding) < 768:
        embedding.extend([0.0] * (768 - len(embedding)))

    async with AsyncSession(db_engine) as session:
        stmt = (
            select(LongTermMemory)
            .where(LongTermMemory.user_id == user_id)
            .order_by(LongTermMemory.embedding.cosine_distance(embedding))
            .limit(top_k)
        )
        res = await session.execute(stmt)
        memories = res.scalars().all()
        
    return [{"content": m.content, "memory_type": m.memory_type} for m in memories]
