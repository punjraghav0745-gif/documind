import logging
import uuid

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.models.schemas import SourceChunk
from app.services.embedder import get_openai_client

logger = logging.getLogger(__name__)
settings = get_settings()

SYSTEM_PROMPT = """You are a precise document Q&A assistant. Answer the user's question using ONLY the provided context chunks.

Rules:
- Base your answer strictly on the context provided
- Cite sources by referencing chunk numbers, e.g. [Chunk 1], [Chunk 3]
- If the context does not contain enough information to answer, say "I don't have enough information in the provided documents to answer this question."
- Be concise and factual
- Never fabricate information not present in the context"""


def _build_context(sources: list[SourceChunk], full_contents: dict[uuid.UUID, str]) -> str:
    parts = []
    for i, source in enumerate(sources, 1):
        content = full_contents.get(source.chunk_id, source.content_preview)
        parts.append(f"[Chunk {i}] (similarity: {source.similarity_score})\n{content}")
    return "\n\n---\n\n".join(parts)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def generate_answer(
    question: str,
    sources: list[SourceChunk],
    full_contents: dict[uuid.UUID, str],
) -> tuple[str, int]:
    """Returns (answer_text, total_tokens_used)."""
    if not sources:
        return "No relevant document chunks were found to answer your question.", 0

    context = _build_context(sources, full_contents)
    user_message = f"Context:\n{context}\n\nQuestion: {question}"

    client = get_openai_client()
    response = await client.chat.completions.create(
        model=settings.openai_chat_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        max_tokens=settings.max_answer_tokens,
        temperature=0.1,
    )

    answer = response.choices[0].message.content or ""
    tokens_used = response.usage.total_tokens if response.usage else 0

    logger.info("Generated answer using %d tokens", tokens_used)
    return answer, tokens_used
