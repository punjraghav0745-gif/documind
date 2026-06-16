from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://documind:documind@localhost:5432/documind"

    # OpenAI
    openai_api_key: str
    openai_embedding_model: str = "text-embedding-3-small"
    openai_chat_model: str = "gpt-4o-mini"
    embedding_dimensions: int = 1536

    # AWS / S3
    aws_s3_bucket: str = "documind-documents"
    aws_region: str = "ap-southeast-2"
    aws_endpoint_url: str | None = None  # Set to http://localhost:4566 for LocalStack
    aws_access_key_id: str = "test"
    aws_secret_access_key: str = "test"

    # Chunking
    chunk_size_tokens: int = 512
    chunk_overlap_tokens: int = 50

    # RAG
    default_top_k: int = 5
    max_answer_tokens: int = 1000

    # Outbox worker
    outbox_poll_interval_seconds: int = 5
    outbox_batch_size: int = 10

    # Retry / DLQ
    embedding_max_retries: int = 3
    embedding_retry_base_delay: float = 1.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
