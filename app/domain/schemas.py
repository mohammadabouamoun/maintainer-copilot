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
