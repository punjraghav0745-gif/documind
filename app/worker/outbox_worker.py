import asyncio
import logging
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.dependencies import AsyncSessionLocal
from app.models.db import OutboxEvent

logger = logging.getLogger(__name__)
settings = get_settings()


async def process_outbox_batch() -> int:
    async with AsyncSessionLocal() as db:
        # SELECT FOR UPDATE SKIP LOCKED — safe for multiple workers
        result = await db.execute(
            select(OutboxEvent)
            .where(OutboxEvent.status == "pending")
            .order_by(OutboxEvent.created_at)
            .limit(settings.outbox_batch_size)
            .with_for_update(skip_locked=True)
        )
        events = result.scalars().all()

        if not events:
            return 0

        for event in events:
            try:
                logger.info("Processing outbox event %s type=%s", event.id, event.event_type)
                # Production: fan out to SNS/SQS here
                event.status = "processed"
                event.processed_at = datetime.utcnow()
            except Exception as e:
                logger.error("Failed to process outbox event %s: %s", event.id, e)
                event.status = "failed"

        await db.commit()
        return len(events)


async def _outbox_loop():
    logger.info("Outbox worker started (poll interval=%ds)", settings.outbox_poll_interval_seconds)
    while True:
        try:
            processed = await process_outbox_batch()
            if processed:
                logger.info("Outbox worker processed %d events", processed)
        except Exception as e:
            logger.error("Outbox worker error: %s", e)
        await asyncio.sleep(settings.outbox_poll_interval_seconds)


async def start_outbox_worker(app):
    task = asyncio.create_task(_outbox_loop())
    app.state.outbox_worker_task = task
