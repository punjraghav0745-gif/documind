import logging
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.db import Chunk
from app.models.schemas import SourceChunk

logger = logging.getLogger(__name__)
settings = get_settings()


async def similarity_search(
    db: AsyncSession,
    query_embedding: list[float],
    top_k: int = 5,
    document_id: uuid.UUID | None = None,
) -> list[SourceChunk]:
    # Build the cosine similarity query using pgvector <=> operator
    # The HNSW index on chunks(embedding vector_cosine_ops) is used automatically
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    if document_id:
        sql = text("""
            SELECT
                id,
                chunk_index,
                content,
                1 - (embedding <=> :embedding ::vector) AS similarity_score
            FROM chunks
            WHERE document_id = :document_id
              AND embedding IS NOT NULL
            ORDER BY embedding <=> :embedding ::vector
            LIMIT :top_k
        """)
        result = await db.execute(sql, {
            "embedding": embedding_str,
            "document_id": str(document_id),
            "top_k": top_k,
        })
    else:
        sql = text("""
            SELECT
                id,
                chunk_index,
                content,
                1 - (embedding <=> :embedding ::vector) AS similarity_score
            FROM chunks
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> :embedding ::vector
            LIMIT :top_k
        """)
        result = await db.execute(sql, {
            "embedding": embedding_str,
            "top_k": top_k,
        })

    rows = result.fetchall()
    sources = [
        SourceChunk(
            chunk_id=row.id,
            chunk_index=row.chunk_index,
            similarity_score=round(float(row.similarity_score), 4),
            content_preview=row.content[:300] + ("..." if len(row.content) > 300 else ""),
        )
        for row in rows
    ]

    logger.info("Similarity search returned %d chunks (top_k=%d, doc=%s)", len(sources), top_k, document_id)
    return sources


async def get_chunk_contents(
    db: AsyncSession,
    chunk_ids: list[uuid.UUID],
) -> dict[uuid.UUID, str]:
    result = await db.execute(
        select(Chunk.id, Chunk.content).where(Chunk.id.in_(chunk_ids))
    )
    return {row.id: row.content for row in result.fetchall()}
