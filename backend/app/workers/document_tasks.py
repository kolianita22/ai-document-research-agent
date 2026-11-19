import asyncio
import uuid
from datetime import datetime, timezone
from sqlalchemy import select

from app.workers.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.models.document import Document
from app.services.processing_service import process_document


async def process_document_async(document_id: str):
    try:
        doc_uuid = uuid.UUID(str(document_id))
    except (ValueError, AttributeError):
        return {
            "status": "failed",
            "message": "Invalid document UUID",
        }

    async with AsyncSessionLocal() as db:

        result = await db.execute(
            select(Document).where(
                Document.id == doc_uuid
            )
        )

        document = result.scalar_one_or_none()

        if not document:
            return {
                "status": "failed",
                "message": "Document not found",
            }

        try:
            document.status = "processing"
            document.error_message = None
            await db.commit()

            chunk_count = await process_document(db, document)

            document.processed_at = datetime.now(timezone.utc)
            await db.commit()

            return {
                "status": "completed",
                "document_id": document_id,
                "chunk_count": chunk_count,
            }

        except Exception as exc:
            await db.rollback()

            # Re-fetch the document in a clean transaction.
            result = await db.execute(
                select(Document).where(
                    Document.id == doc_uuid
                )
            )

            document = result.scalar_one_or_none()

            if document:
                document.status = "failed"
                document.error_message = str(exc)[:1000]
                await db.commit()

            raise


@celery_app.task(
    name="app.workers.document_tasks.process_document_task",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def process_document_task(self, document_id: str):

    try:
        return asyncio.run(
            process_document_async(document_id)
        )

    except Exception as exc:
        raise self.retry(exc=exc)