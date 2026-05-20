from pydantic import BaseModel
from typing import Optional, Dict, Any
import uuid
from fastapi_users import schemas

class Chunk(BaseModel):
    id: str
    source_type: str
    source_id: str
    chunk_index: int
    content: str
    metadata: Dict[str, Any]
    score: Optional[float] = None

class UserRead(schemas.BaseUser[uuid.UUID]):
    role: str

class UserCreate(schemas.BaseUserCreate):
    role: Optional[str] = "user"

class UserUpdate(schemas.BaseUserUpdate):
    role: Optional[str] = None

class WidgetBase(BaseModel):
    allowed_origins: list[str]
    theme: Dict[str, Any]
    greeting: Optional[str] = None
    enabled_tools: list[str] = ["classify_issue", "extract_entities", "summarize_thread", "search_knowledge_base", "write_memory"]

class WidgetCreate(WidgetBase):
    pass

class WidgetUpdate(BaseModel):
    allowed_origins: Optional[list[str]] = None
    theme: Optional[Dict[str, Any]] = None
    greeting: Optional[str] = None
    enabled_tools: Optional[list[str]] = None

class WidgetRead(WidgetBase):
    id: uuid.UUID
    widget_id: uuid.UUID
    created_by: Optional[uuid.UUID]
    created_at: Any  # DateTime string

class WidgetPublicRead(BaseModel):
    theme: Dict[str, Any]
    greeting: Optional[str] = None
    enabled_tools: list[str]
