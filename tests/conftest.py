import asyncio
import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.dependencies import get_db, get_s3_client
from app.main import create_app
from app.models.db import Base

TEST_DB_URL = "postgresql+asyncpg://documind:documind@localhost:5432/documind"

FAKE_EMBEDDING = [0.01] * 1536

SAMPLE_PDF_TEXT = (
    "Artificial intelligence is transforming industries. "
    "Machine learning models learn from data. "
    "Neural networks are inspired by the human brain."
)


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    # NullPool ensures no connection sharing across async contexts
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False, autoflush=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def mock_s3():
    s3_mock = MagicMock()
    s3_mock.head_bucket.return_value = {}
    s3_mock.put_object.return_value = {}
    return s3_mock


@pytest.fixture
def mock_embed():
    with patch("app.routers.ingest.embed_texts", new_callable=AsyncMock) as mock:
        mock.return_value = [FAKE_EMBEDDING]
        yield mock


@pytest.fixture
def mock_embed_single():
    with patch("app.routers.query.embed_text", new_callable=AsyncMock) as mock:
        mock.return_value = FAKE_EMBEDDING
        yield mock


@pytest.fixture
def mock_generate():
    with patch("app.services.generator.generate_answer", new_callable=AsyncMock) as mock:
        mock.return_value = ("This document is about AI and machine learning.", 42)
        yield mock


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 10, SAMPLE_PDF_TEXT)
    return bytes(pdf.output())


@pytest_asyncio.fixture
async def client(db_session, mock_s3) -> AsyncGenerator[AsyncClient, None]:
    # Patch outbox worker so it doesn't spin up a background task in tests
    with patch("app.worker.outbox_worker.start_outbox_worker", new_callable=AsyncMock):
        app = create_app()

        async def override_get_db():
            yield db_session

        def override_get_s3():
            return mock_s3

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_s3_client] = override_get_s3

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
