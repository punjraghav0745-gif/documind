# DocuMind

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/pgvector-336791?logo=postgresql&logoColor=white)
![AWS Lambda](https://img.shields.io/badge/AWS-Lambda-FF9900?logo=awslambda&logoColor=white)
![Terraform](https://img.shields.io/badge/Terraform-7B42BC?logo=terraform&logoColor=white)

Upload a PDF, ask questions about it, get grounded answers with citations back to the source chunks. A RAG API built the way a production service actually needs to be: deduplicated ingestion, atomic outbox-pattern event delivery, HNSW vector search, and a serverless deployment path — not a notebook wrapped in a `/query` endpoint.

Run `docker-compose up` and `uvicorn app.main:app`, then open `http://127.0.0.1:8000` for a live demo UI to upload a PDF and ask questions in the browser.

## Architecture

```
┌─────────────┐     POST /ingest      ┌──────────────────────────────────────────┐
│   Client    │ ──────────────────▶   │              FastAPI App                 │
│             │     POST /ask         │                                          │
│             │ ──────────────────▶   │  ┌──────────┐  ┌──────────────────────┐ │
└─────────────┘                       │  │ Ingest   │  │  Query Router        │ │
                                      │  │ Router   │  │  /ask                │ │
                                      │  └────┬─────┘  └──────────┬───────────┘ │
                                      │       │                    │             │
                                      └───────┼────────────────────┼─────────────┘
                                              │                    │
                          ┌───────────────────┼────────────────────┼──────────────┐
                          │  Services         │                    │              │
                          │  ┌────────────────▼──┐  ┌─────────────▼────────────┐ │
                          │  │ chunker.py        │  │ retriever.py             │ │
                          │  │ pdfplumber +      │  │ pgvector cosine search   │ │
                          │  │ tiktoken chunking │  └─────────────┬────────────┘ │
                          │  └────────────────┬──┘                │              │
                          │  ┌────────────────▼──┐  ┌────────────▼─────────────┐ │
                          │  │ embedder.py       │  │ generator.py             │ │
                          │  │ OpenAI            │  │ GPT-4o-mini              │ │
                          │  │ text-embedding-   │  │ grounded answer +        │ │
                          │  │ 3-small (1536-dim)│  │ source citations         │ │
                          │  └───────────────────┘  └──────────────────────────┘ │
                          └──────────────────────────────────────────────────────┘
                                              │
                          ┌───────────────────▼──────────────────────────────────┐
                          │  Storage                                              │
                          │  ┌─────────────────────┐  ┌────────────────────────┐ │
                          │  │ PostgreSQL+pgvector  │  │ AWS S3                 │ │
                          │  │ documents            │  │ Original PDFs          │ │
                          │  │ chunks (HNSW index)  │  └────────────────────────┘ │
                          │  │ outbox_events        │                             │
                          │  └─────────────────────┘                             │
                          └──────────────────────────────────────────────────────┘
```

**Key patterns:**
- SHA-256 deduplication — uploading the same PDF twice returns the same `document_id`
- Transactional Outbox Pattern — chunk records + outbox event committed atomically
- pgvector HNSW index — sub-millisecond approximate nearest-neighbour search
- `SELECT FOR UPDATE SKIP LOCKED` — outbox worker safe for multiple concurrent instances
- DLQ table — failed embeddings queued for manual replay, never abort full ingestion

## Local Setup

### Prerequisites
- Docker Desktop
- Python 3.11+
- OpenAI API key with credits

### 1. Start infrastructure

```bash
docker-compose up -d
docker-compose ps   # both containers should show (healthy)
```

### 2. Install dependencies

```bash
python -m venv venv
source venv/bin/activate        # Windows: .\venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env and set OPENAI_API_KEY=sk-...
```

### 4. Start the API

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

API docs available at **http://127.0.0.1:8000/docs**, and a browser demo UI at **http://127.0.0.1:8000/**

## API Endpoints

### POST /ingest — Upload a PDF

```bash
curl -X POST http://localhost:8000/ingest \
  -F "file=@/path/to/document.pdf"
```

Response:
```json
{
  "document_id": "47949ef3-bcbc-4a8a-96fd-af5af04a6f04",
  "filename": "document.pdf",
  "chunk_count": 12,
  "deduplicated": false
}
```

### POST /ask — Ask a question

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the main findings?", "document_id": "47949ef3-...", "top_k": 5}'
```

Response:
```json
{
  "answer": "The main findings are... [Chunk 1] [Chunk 3]",
  "sources": [
    {
      "chunk_id": "...",
      "chunk_index": 2,
      "similarity_score": 0.923,
      "content_preview": "The study found that..."
    }
  ],
  "tokens_used": 312,
  "document_id": "47949ef3-..."
}
```

### GET /health

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

## Running Tests

```bash
pytest tests/ -v --cov=app --cov-report=term-missing
```

## Deployment (AWS Lambda)

### Prerequisites
- AWS CLI configured
- Terraform >= 1.6
- Docker

### 1. Build and push container to ECR

```bash
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=ap-southeast-2

aws ecr create-repository --repository-name documind --region $AWS_REGION

aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

docker build -t documind .
docker tag documind:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/documind:latest
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/documind:latest
```

### 2. Deploy with Terraform

```bash
cd infra
terraform init
terraform apply \
  -var="openai_api_key=sk-..." \
  -var="database_url=postgresql+asyncpg://user:pass@host:5432/documind" \
  -var="ecr_image_uri=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/documind:latest"
```

Terraform outputs the public API Gateway URL.
