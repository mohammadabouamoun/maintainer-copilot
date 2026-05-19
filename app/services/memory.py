from app.infra.redaction import redact

async def write_long_term(user_id: int, content: str, memory_type: str, actor_id: int) -> dict:
    """
    Writes a fact to long-term memory.
    Strictly filters the content through our security Redaction Layer prior to any database write.
    """
    # 3.8 Redaction Gate: Scrub keys and sensitive PII first
    content = redact(content)

    # Skeleton placeholder for database writes (Phase 4.5 completion)
    return {
        "status": "stored",
        "user_id": user_id,
        "content": content,
        "memory_type": memory_type,
        "actor_id": actor_id
    }

async def recall_relevant(user_id: int, query: str, top_k: int = 5) -> list:
    """
    Retrieves semantic matches from long-term memory.
    Scrubs queries to avoid leakage of search context.
    """
    query = redact(query)
    return []
