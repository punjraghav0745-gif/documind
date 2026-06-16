-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Documents table: tracks uploaded files with deduplication via content_hash
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename TEXT NOT NULL,
    content_hash TEXT UNIQUE NOT NULL,
    s3_key TEXT NOT NULL,
    chunk_count INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Chunks table: stores text chunks with their 1536-dim OpenAI embeddings
CREATE TABLE IF NOT EXISTS chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- HNSW index for fast approximate cosine similarity search
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Outbox events: Transactional Outbox Pattern for reliable async processing
CREATE TABLE IF NOT EXISTS outbox_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    CONSTRAINT outbox_status_check CHECK (status IN ('pending', 'processed', 'failed'))
);

CREATE INDEX IF NOT EXISTS outbox_events_status_idx ON outbox_events (status, created_at)
    WHERE status = 'pending';

-- DLQ: chunks that failed embedding after all retries
CREATE TABLE IF NOT EXISTS dlq_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id),
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_attempted_at TIMESTAMPTZ,
    CONSTRAINT dlq_status_check CHECK (status IN ('pending', 'replayed', 'exhausted'))
);

-- Idempotency records: cache responses for duplicate requests
CREATE TABLE IF NOT EXISTS idempotency_records (
    key TEXT PRIMARY KEY,
    response JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Expire idempotency records after 24 hours (enforced at app layer)
CREATE INDEX IF NOT EXISTS idempotency_records_created_at_idx
    ON idempotency_records (created_at);
