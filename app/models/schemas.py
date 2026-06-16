import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# --- Ingest ---

class IngestResponse(BaseModel):
    document_id: uuid.UUID
    filename: str
    chunk_count: int
    deduplicated: bool


# --- Query ---

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    document_id: uuid.UUID | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class SourceChunk(BaseModel):
    chunk_id: uuid.UUID
    chunk_index: int
    similarity_score: float
    content_preview: str


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceChunk]
    tokens_used: int
    document_id: uuid.UUID | None = None


# --- DLQ ---

class DLQReplayResponse(BaseModel):
    replayed: int
    failed: int
