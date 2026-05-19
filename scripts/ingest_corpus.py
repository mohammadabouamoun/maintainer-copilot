import os
import json
import uuid
import structlog
import psycopg2
from minio import Minio
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = structlog.get_logger()

# Database and MinIO Configuration (Overriding .env to use localhost mappings)
DB_URL = "postgresql://user:password@localhost:5432/dbname"
MINIO_ENDPOINT = "localhost:9002"
MINIO_ACCESS_KEY = "your_minio_user"
MINIO_SECRET_KEY = "your_minio_password"
BUCKET_NAME = "rag-corpus-snapshots"

def init_db():
    logger.info("Initializing PostgreSQL pgvector table...")
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    
    # Ensure pgvector extension exists
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    
    # Create table for our MiniLM embeddings (384 dimensions)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS corpus_chunks (
            id UUID PRIMARY KEY,
            source_type TEXT,
            source_id TEXT,
            chunk_index INT,
            content TEXT,
            metadata JSONB,
            embedding vector(384)
        );
    """)
    # Clear existing data for idempotency
    cur.execute("TRUNCATE TABLE corpus_chunks;")
    conn.commit()
    return conn, cur

def init_minio():
    logger.info("Initializing MinIO bucket...")
    client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False
    )
    if not client.bucket_exists(BUCKET_NAME):
        client.make_bucket(BUCKET_NAME)
    return client

def chunk_text(text, splitter):
    """Splits text using the recursive character splitter."""
    return splitter.split_text(text)

def load_and_chunk_corpus():
    logger.info("Loading and chunking corpus files...")
    # all-MiniLM-L6-v2 handles up to 256 tokens. 
    # ~4 chars per token = ~1000 chars. We'll use 800 for safety, with 100 overlap.
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
        length_function=len,
        is_separator_regex=False,
    )
    
    final_chunks = []
    
    # 1. Docs
    if os.path.exists("data/corpus/docs.jsonl"):
        with open("data/corpus/docs.jsonl", "r") as f:
            for line in f:
                doc = json.loads(line)
                sub_chunks = chunk_text(doc["text"], text_splitter)
                for i, text in enumerate(sub_chunks):
                    final_chunks.append({
                        "source_type": "doc",
                        "source_id": doc["source"],
                        "chunk_index": i,
                        "content": f"Title: {doc['title']}\n{text}",
                        "metadata": {"title": doc["title"]}
                    })
    
    # 2. Issues
    if os.path.exists("data/corpus/resolved_issues.jsonl"):
        with open("data/corpus/resolved_issues.jsonl", "r") as f:
            for line in f:
                issue = json.loads(line)
                sub_chunks = chunk_text(issue["text"], text_splitter)
                for i, text in enumerate(sub_chunks):
                    final_chunks.append({
                        "source_type": "issue",
                        "source_id": issue["source"],
                        "chunk_index": i,
                        "content": text,
                        "metadata": {"title": issue["title"]}
                    })
                    
    logger.info("Total final chunks generated", count=len(final_chunks))
    return final_chunks

def ingest():
    conn, cur = init_db()
    minio_client = init_minio()
    
    chunks = load_and_chunk_corpus()
    if not chunks:
        logger.error("No chunks to process. Did you run preprocess_corpus.py?")
        return

    logger.info("Loading embedding model (all-MiniLM-L6-v2)...")
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    
    logger.info("Generating embeddings (this may take a minute)...")
    texts = [c["content"] for c in chunks]
    embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=True)
    
    logger.info("Inserting into Postgres (pgvector)...")
    snapshot_data = []
    
    for i, chunk in enumerate(chunks):
        chunk_id = str(uuid.uuid4())
        emb = embeddings[i].tolist()
        
        cur.execute("""
            INSERT INTO corpus_chunks (id, source_type, source_id, chunk_index, content, metadata, embedding)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (chunk_id, chunk["source_type"], chunk["source_id"], chunk["chunk_index"], chunk["content"], json.dumps(chunk["metadata"]), emb))
        
        # Save for snapshot
        chunk["id"] = chunk_id
        chunk["embedding"] = emb
        snapshot_data.append(chunk)

    conn.commit()
    cur.close()
    conn.close()
    
    logger.info("Uploading snapshot to MinIO...")
    snapshot_path = "data/corpus/snapshot.json"
    with open(snapshot_path, "w") as f:
        json.dump(snapshot_data, f)
        
    minio_client.fput_object(BUCKET_NAME, "corpus_snapshot.json", snapshot_path)
    logger.info("Snapshot uploaded to MinIO", bucket=BUCKET_NAME, object="corpus_snapshot.json")
    
    logger.info("Ingestion complete!")

if __name__ == "__main__":
    ingest()
