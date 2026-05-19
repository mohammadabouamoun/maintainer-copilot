import os
import structlog
from openai import AsyncOpenAI
from app.config import get_settings

logger = structlog.get_logger()

class QueryTransformService:
    def __init__(self, client: AsyncOpenAI, model_name: str = "llama-3.1-8b-instant"):
        """
        Initializes the QueryTransformService with an injected AsyncOpenAI client.
        Standard 2: Dependency Injection
        """
        self.client = client
        self.model_name = model_name
        self._prompt_template = self._load_prompt()

    def _load_prompt(self) -> str:
        prompt_path = os.path.join(os.getcwd(), "prompts", "query_rewrite.txt")
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            logger.error("Prompt file not found", path=prompt_path)
            return "Rewrite the following query to be specific for pandas documentation search. Output only the query."

    async def rewrite_query(self, query: str) -> str:
        """
        Uses the injected LLM client to rewrite a vague query into a highly optimized search query.
        """
        logger.info("Transforming query", original_query=query)
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self._prompt_template},
                    {"role": "user", "content": query}
                ],
                temperature=0.0,
                max_tokens=60
            )
            
            rewritten = response.choices[0].message.content.strip()
            
            # Fallback if the LLM hallucinated conversational filler
            if len(rewritten) > 200 or "\n" in rewritten:
                logger.warning("Rewritten query too long or malformed, falling back to original", rewritten=rewritten)
                return query
                
            logger.info("Query transformed", original=query, rewritten=rewritten)
            return rewritten
            
        except Exception as e:
            logger.error("LLM rewrite failed, falling back to original query", error=str(e))
            return query
