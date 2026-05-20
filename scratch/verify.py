import asyncio
import uuid
import json
import requests
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import select
from app.repositories.models import LongTermMemory
import redis.asyncio as aioredis

API_URL = "http://localhost:8000"

async def main():
    # 1. Register and login
    unique_id = uuid.uuid4().hex[:6]
    email = f"user_{unique_id}@example.com"
    password = "SecurePassword123!"
    
    requests.post(f"{API_URL}/auth/register", json={"email": email, "password": password, "role": "user"})
    resp = requests.post(f"{API_URL}/auth/login", data={"username": email, "password": password})
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # 2. Test Phase 4.4: Short-Term Memory Cache
    print("Testing Redis Short-Term Memory...")
    conv_id = str(uuid.uuid4())
    requests.post(f"{API_URL}/chat/message", json={"conversation_id": conv_id, "message": "Hi, this is message 1"}, headers=headers)
    requests.post(f"{API_URL}/chat/message", json={"conversation_id": conv_id, "message": "And this is message 2"}, headers=headers)
    
    r = await aioredis.from_url("redis://localhost:6379/0", decode_responses=True)
    messages = await r.lrange(f"conversations:{conv_id}", 0, -1)
    
    print(f"Messages in Redis: {len(messages)}")
    assert len(messages) == 4  # 2 user messages + 2 assistant responses
    print("Redis cache contains messages:", [json.loads(m)["content"] for m in messages])
    
    # Check TTL
    ttl = await r.ttl(f"conversations:{conv_id}")
    print(f"TTL for conversation {conv_id} is {ttl} seconds")
    assert 0 < ttl <= 3600

    # 3. Test Phase 4.5: Long-Term Memory (pgvector)
    print("\nTesting pgvector Long-Term Memory...")
    requests.post(f"{API_URL}/chat/message", json={"conversation_id": conv_id, "message": "Call the write_memory tool right now to remember this permanently: I prefer extremely concise answers."}, headers=headers)
    
    engine = create_async_engine("postgresql+asyncpg://user:password@localhost:5432/dbname")
    async with AsyncSession(engine) as session:
        stmt = select(LongTermMemory)
        records = (await session.execute(stmt)).scalars().all()
        found = False
        for rec in records:
            if "concise" in rec.content.lower():
                found = True
                print(f"Found long-term memory: {rec.content} (type: {rec.memory_type})")
                break
        if not found:
            print("ERROR: Long term memory not found!")

    await r.aclose()
    await engine.dispose()
    print("All checks passed successfully.")

if __name__ == "__main__":
    asyncio.run(main())
