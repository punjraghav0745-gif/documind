import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.schemas import AskRequest, AskResponse
from app.services.embedder import embed_text
from app.services.generator import generate_answer
from app.services.retriever import get_chunk_contents, similarity_search

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ask", tags=["query"])


@router.post("", response_model=AskResponse)
async def ask_question(
    request: AskRequest,
    db: AsyncSession = Depends(get_db),
):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    # Embed the question using the same model as the chunks
    try:
        query_embedding = await embed_text(request.question)
    except Exception as e:
        logger.error("Failed to embed question: %s", e)
        raise HTTPException(status_code=502, detail="Failed to process question embedding")

    # pgvector cosine similarity search
    sources = await similarity_search(
        db=db,
        query_embedding=query_embedding,
        top_k=request.top_k,
        document_id=request.document_id,
    )

    if not sources:
        return AskResponse(
            answer="No relevant document chunks were found. Please ingest a document first.",
            sources=[],
            tokens_used=0,
            document_id=request.document_id,
        )

    # Fetch full chunk content for the prompt (previews are truncated)
    chunk_ids = [s.chunk_id for s in sources]
    full_contents = await get_chunk_contents(db, chunk_ids)

    # Generate grounded answer with GPT-4o-mini
    try:
        answer, tokens_used = await generate_answer(
            question=request.question,
            sources=sources,
            full_contents=full_contents,
        )
    except Exception as e:
        logger.error("Failed to generate answer: %s", e)
        raise HTTPException(status_code=502, detail="Failed to generate answer")

    return AskResponse(
        answer=answer,
        sources=sources,
        tokens_used=tokens_used,
        document_id=request.document_id,
    )
