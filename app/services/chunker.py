import logging
from dataclasses import dataclass

import pdfplumber
import tiktoken

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class TextChunk:
    content: str
    chunk_index: int
    token_count: int


def extract_text_from_pdf(file_bytes: bytes) -> str:
    import io
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        pages = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
    full_text = "\n\n".join(pages)
    if not full_text.strip():
        raise ValueError("No extractable text found in PDF")
    return full_text


def chunk_text(text: str, chunk_size: int | None = None, overlap: int | None = None) -> list[TextChunk]:
    chunk_size = chunk_size or settings.chunk_size_tokens
    overlap = overlap or settings.chunk_overlap_tokens

    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)

    if not tokens:
        return []

    chunks: list[TextChunk] = []
    start = 0
    chunk_index = 0

    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunk_tokens = tokens[start:end]
        chunk_text_str = enc.decode(chunk_tokens)

        chunks.append(TextChunk(
            content=chunk_text_str.strip(),
            chunk_index=chunk_index,
            token_count=len(chunk_tokens),
        ))

        chunk_index += 1
        # Advance by chunk_size - overlap so consecutive chunks share overlap tokens
        start += chunk_size - overlap

        # Guard against infinite loop if overlap >= chunk_size
        if chunk_size <= overlap:
            break

    logger.info("Chunked text into %d chunks (chunk_size=%d, overlap=%d)", len(chunks), chunk_size, overlap)
    return chunks


def extract_and_chunk(file_bytes: bytes) -> list[TextChunk]:
    text = extract_text_from_pdf(file_bytes)
    return chunk_text(text)
