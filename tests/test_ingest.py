import hashlib

import pytest

from tests.conftest import FAKE_EMBEDDING


@pytest.mark.asyncio
async def test_ingest_success(client, sample_pdf_bytes, mock_embed):
    response = await client.post(
        "/ingest",
        files={"file": ("test.pdf", sample_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    data = response.json()
    assert "document_id" in data
    assert data["filename"] == "test.pdf"
    assert data["chunk_count"] >= 1
    assert data["deduplicated"] is False


@pytest.mark.asyncio
async def test_ingest_deduplication(client, sample_pdf_bytes, mock_embed):
    # First upload
    r1 = await client.post(
        "/ingest",
        files={"file": ("test.pdf", sample_pdf_bytes, "application/pdf")},
    )
    assert r1.status_code == 200
    doc_id_1 = r1.json()["document_id"]

    # Second upload of identical file — must return same document_id
    r2 = await client.post(
        "/ingest",
        files={"file": ("test.pdf", sample_pdf_bytes, "application/pdf")},
    )
    assert r2.status_code == 200
    doc_id_2 = r2.json()["document_id"]

    assert doc_id_1 == doc_id_2


@pytest.mark.asyncio
async def test_ingest_rejects_non_pdf(client):
    response = await client.post(
        "/ingest",
        files={"file": ("test.txt", b"hello world", "text/plain")},
    )
    assert response.status_code == 400
    assert "PDF" in response.json()["detail"]


@pytest.mark.asyncio
async def test_ingest_empty_file(client):
    response = await client.post(
        "/ingest",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_ingest_stores_chunks_with_embeddings(client, sample_pdf_bytes, mock_embed):
    response = await client.post(
        "/ingest",
        files={"file": ("test.pdf", sample_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    mock_embed.assert_called_once()
