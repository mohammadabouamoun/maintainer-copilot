import pytest
import uuid
import time
import json
import asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.main import app
from app.infra.redis_client import get_redis_client
from app.repositories.models import LongTermMemory

@pytest.mark.asyncio
async def test_short_term_memory_redis():
    """Verifies that conversation history is stored in Redis with TTL."""
    unique_id = uuid.uuid4().hex[:6]
    user_email = f"redis_user_{unique_id}@example.com"
    password = "SecurePassword123!"
    conversation_id = str(uuid.uuid4())

    with TestClient(app) as client:
        # Register & Login
        client.post("/auth/register", json={"email": user_email, "password": password, "role": "user"})
        token = client.post("/auth/login", data={"username": user_email, "password": password}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Send a message
        res1 = client.post(
            "/chat/message",
            json={"conversation_id": conversation_id, "message": "Hello, this is a test for Redis."},
            headers=headers
        )
        assert res1.status_code == 200

        # Give the background tasks a moment if any
        await asyncio.sleep(1)

        # Check Redis
        redis = get_redis_client()
        key = f"conversations:{conversation_id}"
        messages = await redis.lrange(key, 0, -1)
        
        # We expect 2 messages: user's message + assistant's response
        assert len(messages) == 2
        
        first_msg = json.loads(messages[0])
        assert first_msg["role"] == "user"
        assert first_msg["content"] == "Hello, this is a test for Redis."
        
        second_msg = json.loads(messages[1])
        assert second_msg["role"] == "assistant"

        # Verify TTL is set (should be around 3600)
        ttl = await redis.ttl(key)
        assert 0 < ttl <= 3600

        # Simulate TTL expiration
        await redis.expire(key, 1)
        await asyncio.sleep(1.5)
        
        expired_messages = await redis.lrange(key, 0, -1)
        assert len(expired_messages) == 0

    print("\nSuccessfully verified Redis caching and TTL!")

@pytest.mark.asyncio
async def test_long_term_memory_pgvector():
    """Verifies that semantic preferences are extracted and stored into pgvector."""
    unique_id = uuid.uuid4().hex[:6]
    user_email = f"pgvector_user_{unique_id}@example.com"
    password = "SecurePassword123!"
    conversation_id = str(uuid.uuid4())

    with TestClient(app) as client:
        client.post("/auth/register", json={"email": user_email, "password": password, "role": "user"})
        token = client.post("/auth/login", data={"username": user_email, "password": password}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Ask the assistant to remember a preference
        res = client.post(
            "/chat/message",
            json={"conversation_id": conversation_id, "message": "Remember that I prefer extremely concise answers."},
            headers=headers
        )
        assert res.status_code == 200

        # Read the stream to consume it
        stream_chunks = [chunk.decode("utf-8") for chunk in res.iter_lines() if chunk and isinstance(chunk, bytes)]
        full_text = "".join(stream_chunks).lower()
        print(f"\nAssistant Response: {full_text}")
        
        # Check Postgres for the memory
        db_engine = app.state.db_engine
        async with AsyncSession(db_engine) as session:
            stmt = select(LongTermMemory)
            records = (await session.execute(stmt)).scalars().all()
            
            # At least one record should belong to our test user with semantic memory type
            found = False
            for rec in records:
                if "concise" in rec.content.lower():
                    found = True
                    assert rec.memory_type == "semantic"
                    assert len(rec.embedding) == 768  # Verify the padding worked
                    break
                    
            assert found, "Long term memory record was not created!"
    
    print("\nSuccessfully verified pgvector Long-Term Memory integration!")
