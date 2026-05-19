from pydantic import BaseModel, Field

class ClassifyRequest(BaseModel):
    text: str = Field(..., description="The issue text to classify")

class ClassifyResponse(BaseModel):
    label: str = Field(..., description="The predicted label (bug, feature, docs, or question)")
    confidence: float = Field(..., description="The prediction confidence score between 0.0 and 1.0")
    latency_ms: float = Field(..., description="The inference execution time in milliseconds")

class NerRequest(BaseModel):
    text: str = Field(..., description="The issue text to perform NER extraction on")

class NerEntity(BaseModel):
    text: str = Field(..., description="The extracted entity text")
    label: str = Field(..., description="The entity classification label")
    start: int = Field(..., description="The start character index of the entity in the source text")
    end: int = Field(..., description="The end character index of the entity in the source text")

class NerResponse(BaseModel):
    entities: list[NerEntity] = Field(default=[], description="The list of extracted entities")

class SummarizeRequest(BaseModel):
    text: str = Field(..., description="The issue text thread or details to summarize")
    max_length: int = Field(default=150, description="The maximum word/token length of the generated summary")

class SummarizeResponse(BaseModel):
    summary: str = Field(..., description="The condensed issue summary")


