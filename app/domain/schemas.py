from pydantic import BaseModel
from typing import Optional, Dict, Any

class Chunk(BaseModel):
    id: str
    source_type: str
    source_id: str
    chunk_index: int
    content: str
    metadata: Dict[str, Any]
    score: Optional[float] = None
