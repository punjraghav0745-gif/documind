import logging
from datetime import datetime

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=settings.embedding_retry_base_delay, min=1, max=10),
    reraise=True,
)
async def embed_text(text: str) -> list[float]:
    client = get_openai_client()
    response = await client.embeddings.create(
        input=text,
        model=settings.openai_embedding_model,
        dimensions=settings.embedding_dimensions,
    )
    return response.data[0].embedding


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts in a single API call (max 2048 inputs per request)."""
    if not texts:
        return []

    client = get_openai_client()

    @retry(
        stop=stop_after_attempt(settings.embedding_max_retries),
        wait=wait_exponential(multiplier=settings.embedding_retry_base_delay, min=1, max=10),
        reraise=True,
    )
    async def _call() -> list[list[float]]:
        response = await client.embeddings.create(
            input=texts,
            model=settings.openai_embedding_model,
            dimensions=settings.embedding_dimensions,
        )
        # API returns embeddings in the same order as input
        return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]

    return await _call()
