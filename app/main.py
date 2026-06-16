import logging

import boto3
from botocore.exceptions import ClientError
from fastapi import FastAPI

from app.config import get_settings
from app.dependencies import get_s3_client
from app.routers import ingest, query

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


def create_app() -> FastAPI:
    app = FastAPI(title="DocuMind", version="1.0.0", description="Production-grade RAG API")

    @app.on_event("startup")
    async def startup():
        # Ensure S3 bucket exists (creates it in LocalStack on first run)
        try:
            s3 = get_s3_client()
            s3.head_bucket(Bucket=settings.aws_s3_bucket)
            logger.info("S3 bucket %s already exists", settings.aws_s3_bucket)
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchBucket"):
                s3.create_bucket(
                    Bucket=settings.aws_s3_bucket,
                    CreateBucketConfiguration={"LocationConstraint": settings.aws_region},
                )
                logger.info("Created S3 bucket %s", settings.aws_s3_bucket)
            else:
                logger.warning("Could not verify S3 bucket: %s", e)

        # Start outbox worker as background task
        from app.worker.outbox_worker import start_outbox_worker
        await start_outbox_worker(app)

    app.include_router(ingest.router)
    app.include_router(query.router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
