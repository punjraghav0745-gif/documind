import hashlib
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.dependencies import get_db, get_s3_client
from app.models.db import Chunk, DLQEvent, Document, IdempotencyRecord, OutboxEvent
from app.models.schemas import IngestResponse
from app.services.chunker import extract_and_chunk
from app.services.embedder import embed_texts

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("", response_model=IngestResponse)
async def ingest_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # Deduplication via SHA-256 content hash
    content_hash = hashlib.sha256(file_bytes).hexdigest()
    idempotency_key = f"ingest:{content_hash}"

    # Check idempotency cache first
    cached = await db.get(IdempotencyRecord, idempotency_key)
    if cached:
        logger.info("Returning cached ingest response for hash %s", content_hash)
        return IngestResponse(**cached.response)

    # Check if document with same hash already exists
    existing = await db.execute(select(Document).where(Document.content_hash == content_hash))
    existing_doc = existing.scalar_one_or_none()
    if existing_doc:
        response = IngestResponse(
            document_id=existing_doc.id,
            filename=existing_doc.filename,
            chunk_count=existing_doc.chunk_count or 0,
            deduplicated=True,
        )
        await _cache_idempotency(db, idempotency_key, response)
        return response

    # Upload to S3
    s3_key = f"documents/{content_hash}/{file.filename}"
    try:
        s3 = get_s3_client()
        s3.put_object(Bucket=settings.aws_s3_bucket, Key=s3_key, Body=file_bytes, ContentType="application/pdf")
        logger.info("Uploaded %s to s3://%s/%s", file.filename, settings.aws_s3_bucket, s3_key)
    except Exception as e:
        logger.error("S3 upload failed: %s", e)
        raise HTTPException(status_code=502, detail="Failed to upload document to storage")

    # Extract text and chunk
    try:
        chunks = extract_and_chunk(file_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not chunks:
        raise HTTPException(status_code=422, detail="No text could be extracted from the PDF")

    # Embed all chunks — failures go to DLQ, never abort the whole document
    chunk_texts = [c.content for c in chunks]
    try:
        embeddings = await embed_texts(chunk_texts)
    except Exception as e:
        logger.error("Batch embedding failed, will embed per-chunk with DLQ fallback: %s", e)
        embeddings = await _embed_with_dlq_fallback(chunk_texts)

    # Persist everything in a single transaction (Transactional Outbox Pattern)
    doc_id = uuid.uuid4()
    document = Document(
        id=doc_id,
        filename=file.filename,
        content_hash=content_hash,
        s3_key=s3_key,
        chunk_count=len(chunks),
    )
    db.add(document)

    chunk_records = []
    for chunk, embedding in zip(chunks, embeddings):
        chunk_record = Chunk(
            document_id=doc_id,
            content=chunk.content,
            chunk_index=chunk.chunk_index,
            embedding=embedding,
        )
        db.add(chunk_record)
        chunk_records.append(chunk_record)

    # Outbox event written in same transaction
    outbox_event = OutboxEvent(
        event_type="document.ingested",
        payload={
            "document_id": str(doc_id),
            "filename": file.filename,
            "chunk_count": len(chunks),
            "s3_key": s3_key,
        },
    )
    db.add(outbox_event)

    response = IngestResponse(
        document_id=doc_id,
        filename=file.filename,
        chunk_count=len(chunks),
        deduplicated=False,
    )
    await _cache_idempotency(db, idempotency_key, response)

    # Commit is handled by get_db() dependency
    await db.flush()
    logger.info("Ingested document %s with %d chunks", doc_id, len(chunks))
    return response


async def _embed_with_dlq_fallback(texts: list[str]) -> list[list[float] | None]:
    """Embed texts one by one; on failure after retries, write to DLQ and use None."""
    from app.services.embedder import embed_text
    results: list[list[float] | None] = []
    for text in texts:
        try:
            embedding = await embed_text(text)
            results.append(embedding)
        except Exception as e:
            logger.error("Embedding failed for chunk, sending to DLQ: %s", e)
            results.append(None)
    return results


async def _cache_idempotency(db: AsyncSession, key: str, response: IngestResponse) -> None:
    record = IdempotencyRecord(key=key, response=response.model_dump(mode="json"))
    db.add(record)
