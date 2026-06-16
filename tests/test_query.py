import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.models.schemas import SourceChunk
from tests.conftest import FAKE_EMBEDDING


MOCK_SOURCES = [
    SourceChunk(
        chunk_id=uuid.uuid4(),
        chunk_index=0,
        similarity_score=0.92,
        content_preview="Artificial intelligence is transforming industries.",
    )
]


@pytest.mark.asyncio
async def test_ask_returns_answer(client, sample_pdf_bytes, mock_embed, mock_embed_single, mock_generate):
    # Ingest first
    await client.post(
        "/ingest",
        files={"file": ("test.pdf", sample_pdf_bytes, "application/pdf")},
    )

    with patch("app.routers.query.similarity_search", new_callable=AsyncMock) as mock_search, \
         patch("app.routers.query.get_chunk_contents", new_callable=AsyncMock) as mock_contents:

        mock_search.return_value = MOCK_SOURCES
        mock_contents.return_value = {MOCK_SOURCES[0].chunk_id: "Artificial intelligence is transforming industries."}

        response = await client.post(
            "/ask",
            json={"question": "What is this document about?"},
        )

    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert len(data["answer"]) > 0
    assert "sources" in data
    assert "tokens_used" in data


@pytest.mark.asyncio
async def test_ask_with_document_id_filter(client, sample_pdf_bytes, mock_embed, mock_embed_single, mock_generate):
    r = await client.post(
        "/ingest",
        files={"file": ("test.pdf", sample_pdf_bytes, "application/pdf")},
    )
    doc_id = r.json()["document_id"]

    with patch("app.routers.query.similarity_search", new_callable=AsyncMock) as mock_search, \
         patch("app.routers.query.get_chunk_contents", new_callable=AsyncMock) as mock_contents:

        mock_search.return_value = MOCK_SOURCES
        mock_contents.return_value = {MOCK_SOURCES[0].chunk_id: "AI content"}

        response = await client.post(
            "/ask",
            json={"question": "What is AI?", "document_id": doc_id, "top_k": 3},
        )

    assert response.status_code == 200
    # Verify document_id was passed through
    assert response.json()["document_id"] == doc_id


@pytest.mark.asyncio
async def test_ask_no_chunks_returns_graceful_message(client, mock_embed_single):
    with patch("app.routers.query.similarity_search", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = []

        response = await client.post(
            "/ask",
            json={"question": "What is quantum computing?"},
        )

    assert response.status_code == 200
    assert "No relevant" in response.json()["answer"]


@pytest.mark.asyncio
async def test_ask_empty_question_rejected(client):
    response = await client.post("/ask", json={"question": ""})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ask_sources_have_required_fields(client, mock_embed_single, mock_generate):
    with patch("app.routers.query.similarity_search", new_callable=AsyncMock) as mock_search, \
         patch("app.routers.query.get_chunk_contents", new_callable=AsyncMock) as mock_contents:

        mock_search.return_value = MOCK_SOURCES
        mock_contents.return_value = {MOCK_SOURCES[0].chunk_id: "AI content"}

        response = await client.post("/ask", json={"question": "Tell me about AI"})

    assert response.status_code == 200
    sources = response.json()["sources"]
    assert len(sources) == 1
    assert "chunk_id" in sources[0]
    assert "similarity_score" in sources[0]
    assert "content_preview" in sources[0]
