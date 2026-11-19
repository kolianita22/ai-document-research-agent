import uuid
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.schemas.document import (
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentStatusResponse,
    DocumentUploadResponse,
)
from app.services.storage import storage_service

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a document (PDF, DOCX, TXT) with content validation and storage.
    Enforces maximum size (20MB) and stores file securely outside public directories.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    # Read uploaded content
    content = await file.read()
    sanitized_filename = storage_service.sanitize_filename(file.filename)

    # Validate and save file to secure storage
    stored_filename, storage_path, file_type = await storage_service.save_file(
        sanitized_filename, content
    )

    # Optional fast metadata extraction (e.g. page count for PDF)
    page_count = None
    if file_type == "pdf":
        try:
            import pymupdf
            with pymupdf.open(stream=content, filetype="pdf") as doc_pdf:
                page_count = len(doc_pdf)
        except Exception:
            page_count = None

    # Save document record in PostgreSQL
    new_doc = Document(
        user_id=current_user.id,
        original_filename=sanitized_filename,
        stored_filename=stored_filename,
        file_type=file_type,
        file_size=len(content),
        storage_path=storage_path,
        page_count=page_count,
        status=DocumentStatus.UPLOADED,
    )

    db.add(new_doc)
    try:
        await db.commit()
        await db.refresh(new_doc)
    except Exception as exc:
        await db.rollback()
        # Clean up stored file if database commit fails
        await storage_service.delete_file(storage_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record document metadata: {str(exc)}",
        )

    # Dispatch asynchronous background processing via Celery
    try:
        from app.workers.document_tasks import process_document_task
        process_document_task.delay(str(new_doc.id))
    except Exception:
        # Non-blocking fallback if broker is offline during local test runs
        pass

    return DocumentUploadResponse(
        id=new_doc.id,
        original_filename=new_doc.original_filename,
        file_type=new_doc.file_type,
        file_size=new_doc.file_size,
        status=new_doc.status,
        created_at=new_doc.created_at,
        message="Document uploaded successfully",
    )


@router.get(
    "/",
    response_model=DocumentListResponse,
)
async def list_documents(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all documents belonging to the authenticated user with pagination and optional status filter.
    Excludes documents currently marked as deleting.
    """
    base_query = select(Document).where(
        Document.user_id == current_user.id,
        Document.status != DocumentStatus.DELETING,
    )

    if status_filter:
        clean_status = status_filter.strip().lower()
        base_query = base_query.where(Document.status == clean_status)

    # Count total matching
    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate and order by newest first
    offset = (page - 1) * page_size
    query = base_query.order_by(Document.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(query)
    documents = result.scalars().all()

    return DocumentListResponse(
        items=[DocumentDetailResponse.model_validate(doc) for doc in documents],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentDetailResponse,
)
async def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get detailed information for a specific document.
    Enforces user ownership.
    """
    query = select(Document).where(Document.id == document_id)
    result = await db.execute(query)
    document = result.scalar_one_or_none()

    if not document or document.status == DocumentStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    if document.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: you do not own this document",
        )

    return DocumentDetailResponse.model_validate(document)


@router.get(
    "/{document_id}/status",
    response_model=DocumentStatusResponse,
)
async def get_document_status(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get current processing status of a document.
    Enforces user ownership.
    """
    query = select(Document).where(Document.id == document_id)
    result = await db.execute(query)
    document = result.scalar_one_or_none()

    if not document or document.status == DocumentStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    if document.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: you do not own this document",
        )

    return DocumentStatusResponse.model_validate(document)


@router.delete(
    "/{document_id}",
)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a document and its stored physical file.
    Enforces user ownership.
    """
    query = select(Document).where(Document.id == document_id)
    result = await db.execute(query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    if document.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: you do not own this document",
        )

    # Mark as deleting to prevent concurrent access
    document.status = DocumentStatus.DELETING
    storage_path = document.storage_path

    # Delete record from database
    await db.delete(document)
    await db.commit()

    # Clean up file on disk
    if storage_path:
        await storage_service.delete_file(storage_path)

    return {
        "status": "success",
        "message": "Document deleted successfully",
    }


@router.post(
    "/{document_id}/reprocess",
    response_model=DocumentDetailResponse,
)
async def reprocess_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retry/reprocess a failed or completed document.
    Resets status to 'uploaded' and clears previous error messages.
    """
    query = select(Document).where(Document.id == document_id)
    result = await db.execute(query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    if document.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: you do not own this document",
        )

    if document.status == DocumentStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot reprocess a document that is being deleted",
        )

    document.status = DocumentStatus.UPLOADED
    document.error_message = None
    document.processed_at = None

    await db.commit()
    await db.refresh(document)

    # Dispatch asynchronous background processing via Celery
    try:
        from app.workers.document_tasks import process_document_task
        process_document_task.delay(str(document.id))
    except Exception:
        pass

    return DocumentDetailResponse.model_validate(document)
