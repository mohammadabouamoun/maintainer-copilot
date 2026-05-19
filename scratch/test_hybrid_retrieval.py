import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sentence_transformers import SentenceTransformer
from app.services.retrieval import RetrievalService

async def main():
    # Use asyncpg for standard asynchronous I/O
    db_url = "postgresql+asyncpg://user:password@localhost:5432/dbname"
    engine = create_async_engine(db_url)
    
    print("Loading embedding model...")
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    
    print("Initializing RetrievalService...")
    service = RetrievalService(engine=engine, embedding_model=model)
    
    query = "How do I group by multiple columns and calculate the mean?"
    print(f"\\nQuerying: '{query}'")
    
    results = await service.hybrid_retrieve(query=query, top_k=5)
    
    print(f"\\nFound {len(results)} results:")
    for i, res in enumerate(results):
        print(f"\\n--- Result {i+1} (RRF Score: {res.score}) ---")
        print(f"Source Type: {res.source_type} | Source ID: {res.source_id}")
        # Print snippet
        snippet = res.content[:200].replace('\\n', ' ') + "..."
        print(f"Snippet: {snippet}")
        
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
