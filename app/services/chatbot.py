import os
import json
import uuid
import httpx
import structlog
from typing import AsyncIterator, List, Dict, Any, Optional
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy import select
from minio import Minio

from app.config import Settings
from app.repositories.models import Conversation, Message
from app.services.memory import recall_relevant, write_long_term
from app.services.rag_service import RAGService

logger = structlog.get_logger()

class ChatbotService:
    def __init__(
        self,
        openai_client: AsyncOpenAI,
        db_engine: AsyncEngine,
        minio_client: Minio,
        rag_service: RAGService,
        settings: Settings
    ):
        """
        Initializes the ChatbotService with constructor-injected dependencies (Standard 2).
        """
        self.openai_client = openai_client
        self.db_engine = db_engine
        self.minio_client = minio_client
        self.rag_service = rag_service
        self.settings = settings
        self._system_prompt_base = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        prompt_path = os.path.join(os.getcwd(), "prompts", "system.txt")
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            logger.error("System prompt template not found", path=prompt_path)
            return "You are Maintainer's Copilot, a helpful open-source assistant."

    async def _load_history(self, conversation_id: str) -> List[Message]:
        """Loads previous conversation messages from the database."""
        conv_uuid = uuid.UUID(conversation_id)
        async with AsyncSession(self.db_engine) as session:
            stmt = select(Message).where(Message.conversation_id == conv_uuid).order_by(Message.created_at.asc())
            res = await session.execute(stmt)
            return list(res.scalars().all())

    async def _ensure_conversation(self, conversation_id: str, user_id: uuid.UUID) -> None:
        """Ensures that the conversation record exists in the database."""
        conv_uuid = uuid.UUID(conversation_id)
        async with AsyncSession(self.db_engine) as session:
            async with session.begin():
                stmt = select(Conversation).where(Conversation.id == conv_uuid)
                res = await session.execute(stmt)
                conversation = res.scalar_one_or_none()
                if not conversation:
                    conversation = Conversation(id=conv_uuid, user_id=user_id)
                    session.add(conversation)

    async def _save_message(self, conversation_id: str, role: str, content: str) -> None:
        """Persists a new message to the database."""
        conv_uuid = uuid.UUID(conversation_id)
        async with AsyncSession(self.db_engine) as session:
            async with session.begin():
                msg = Message(
                    conversation_id=conv_uuid,
                    role=role,
                    content=content
                )
                session.add(msg)

    # --- Tool implementations with exception shields ---
    async def _tool_classify_issue(self, text: str) -> Dict[str, Any]:
        logger.info("Chatbot executing tool: classify_issue")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self.settings.modelserver_url}/classify",
                    json={"text": text}
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error("classify_issue tool failure", error=str(e))
            return {"error": "ToolFailure", "details": f"Issue classification service is offline: {str(e)}"}

    async def _tool_extract_entities(self, text: str) -> Dict[str, Any]:
        logger.info("Chatbot executing tool: extract_entities")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self.settings.modelserver_url}/ner",
                    json={"text": text}
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error("extract_entities tool failure", error=str(e))
            return {"error": "ToolFailure", "details": f"Named Entity Recognition service is offline: {str(e)}"}

    async def _tool_summarize_thread(self, text: str, max_length: int = 150) -> Dict[str, Any]:
        logger.info("Chatbot executing tool: summarize_thread")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self.settings.modelserver_url}/summarize",
                    json={"text": text, "max_length": max_length}
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error("summarize_thread tool failure", error=str(e))
            return {"error": "ToolFailure", "details": f"Summarization service is offline: {str(e)}"}

    async def _tool_search_knowledge_base(self, query: str) -> Dict[str, Any]:
        logger.info("Chatbot executing tool: search_knowledge_base", query=query)
        try:
            answer, chunks = await self.rag_service.query(
                question=query,
                conversation_id=None,
                metadata_filter=None
            )
            return {
                "answer": answer,
                "chunks": [c.model_dump() for c in chunks]
            }
        except Exception as e:
            logger.error("search_knowledge_base tool failure", error=str(e))
            return {"error": "ToolFailure", "details": f"Knowledge base search failed: {str(e)}"}

    async def _tool_write_memory(self, user_id: uuid.UUID, content: str, memory_type: str = "semantic") -> Dict[str, Any]:
        logger.info("Chatbot executing tool: write_memory", content=content, memory_type=memory_type)
        try:
            # actor_id is user_id for user preference memorization
            result = await write_long_term(
                user_id=user_id,
                content=content,
                memory_type=memory_type,
                actor_id=user_id
            )
            return result
        except Exception as e:
            logger.error("write_memory tool failure", error=str(e))
            return {"error": "ToolFailure", "details": f"Failed to store memory: {str(e)}"}

    async def chat(
        self,
        conversation_id: str,
        user_message: str,
        user_id: uuid.UUID
    ) -> AsyncIterator[str]:
        """
        The Chatbot Service core loop:
        1. Loads history
        2. Recalls relevant long term memories
        3. Invokes tool calling loops
        4. Streams final response
        5. Persists messages
        """
        logger.info("Starting chatbot interaction session", conversation_id=conversation_id, user_id=str(user_id))

        # Ensure conversation structure exists
        await self._ensure_conversation(conversation_id, user_id)

        # 1. Load history
        history = await self._load_history(conversation_id)

        # 2. Recall relevant long-term memories
        memories = await recall_relevant(user_id=user_id, query=user_message)
        system_prompt = self._system_prompt_base
        if memories:
            memory_list = "\n".join([f"- {m['content']}" for m in memories if isinstance(m, dict) and "content" in m])
            system_prompt += f"\n\nRetrieved Long-term User Context/Preferences:\n{memory_list}"

        # 3. Construct message array
        messages = [{"role": "system", "content": system_prompt}]
        for msg in history:
            messages.append({"role": msg.role, "content": msg.content})
        
        # Append user message
        messages.append({"role": "user", "content": user_message})

        # Define tools schema
        tools_def = [
            {
                "type": "function",
                "function": {
                    "name": "classify_issue",
                    "description": "Classifies raw issue reports as a bug, feature, docs, or question.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string", "description": "The raw issue report text"}
                        },
                        "required": ["text"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "extract_entities",
                    "description": "Extracts library, language, and core code entities from issue text.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string", "description": "The raw issue report text"}
                        },
                        "required": ["text"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "summarize_thread",
                    "description": "Summarizes issue thread or description detail logs.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string", "description": "The text body to summarize"},
                            "max_length": {"type": "integer", "description": "Maximum generated length constraint", "default": 150}
                        },
                        "required": ["text"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_knowledge_base",
                    "description": "Searches documentation knowledge base using pandas hybrid retrieval.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "The search query keywords"}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "write_memory",
                    "description": "Write a fact to long-term memory. Only call when explicitly asked by the user to remember something.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string", "description": "The user fact or preference to remember permanently"},
                            "memory_type": {"type": "string", "description": "Memory category (episodic, semantic, procedural)", "default": "semantic"}
                        },
                        "required": ["content"]
                    }
                }
            }
        ]

        # Iteratively resolve tool calls until the LLM yields a final response
        while True:
            response = await self.openai_client.chat.completions.create(
                model=self.settings.llm_model,
                messages=messages,
                tools=tools_def,
                tool_choice="auto",
                temperature=0.0
            )

            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls

            if not tool_calls:
                break

            # Append the assistant's message requesting tool calls
            messages.append(response_message)

            # Resolve each tool call sequentially
            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)
                tool_id = tool_call.id

                try:
                    if tool_name == "classify_issue":
                        result = await self._tool_classify_issue(tool_args["text"])
                    elif tool_name == "extract_entities":
                        result = await self._tool_extract_entities(tool_args["text"])
                    elif tool_name == "summarize_thread":
                        result = await self._tool_summarize_thread(tool_args["text"], tool_args.get("max_length", 150))
                    elif tool_name == "search_knowledge_base":
                        result = await self._tool_search_knowledge_base(tool_args["query"])
                    elif tool_name == "write_memory":
                        result = await self._tool_write_memory(user_id, tool_args["content"], tool_args.get("memory_type", "semantic"))
                    else:
                        result = {"error": "ToolFailure", "details": f"Unknown tool name: {tool_name}"}
                except Exception as e:
                    logger.error("Internal tool dispatch error", tool_name=tool_name, error=str(e))
                    result = {"error": "ToolFailure", "details": str(e)}

                # Append the tool call response
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "name": tool_name,
                    "content": json.dumps(result)
                })

        # Save user message to database
        await self._save_message(conversation_id, "user", user_message)

        # Do a final streaming call to stream tokens back
        stream = await self.openai_client.chat.completions.create(
            model=self.settings.llm_model,
            messages=messages,
            temperature=0.7,
            stream=True
        )

        full_response = ""
        async for chunk in stream:
            content = chunk.choices[0].delta.content or ""
            if content:
                full_response += content
                yield content

        # Save assistant message to database
        if full_response:
            await self._save_message(conversation_id, "assistant", full_response)
