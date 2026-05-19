import asyncio
import os
from openai import AsyncOpenAI
from app.services.transform import QueryTransformService
from dotenv import load_dotenv

async def main():
    load_dotenv()
    
    api_key = os.environ.get("LLM_API_KEY")
    base_url = os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    model_name = os.environ.get("LLM_MODEL", "llama-3.1-8b-instant")
    
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    
    service = QueryTransformService(client=client, model_name=model_name)
    
    vague_query = "why does it not work with Python 3.12"
    print(f"Original Vague Query: '{vague_query}'")
    
    rewritten_query = await service.rewrite_query(vague_query)
    print(f"\\nRewritten Query: '{rewritten_query}'")

if __name__ == "__main__":
    asyncio.run(main())
