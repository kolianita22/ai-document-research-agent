from pathlib import Path
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_chunk import DocumentChunk

from app.processors.pdf_processor import extract_pdf
from app.processors.docx_processor import extract_docx
from app.processors.txt_processor import extract_txt
from app.processors.text_chunker import create_document_chunks


async def process_document(
    db: AsyncSession,
    document: Document,
) -> int:

    file_path = Path(document.storage_path)

    if not file_path.exists():
        raise FileNotFoundError("Stored document file not found")

    extension = file_path.suffix.lower()

    if extension == ".pdf":
        extracted_pages = extract_pdf(str(file_path))

    elif extension == ".docx":
        extracted_pages = extract_docx(str(file_path))

    elif extension == ".txt":
        extracted_pages = extract_txt(str(file_path))

    else:
        raise ValueError("Unsupported document format")

    chunks = create_document_chunks(extracted_pages)

    if not chunks:
        raise ValueError("No text chunks were generated")

    # Reprocessing should replace old chunks, not duplicate them.
    await db.execute(
        delete(DocumentChunk).where(
            DocumentChunk.document_id == document.id
        )
    )

    chunk_objects = []

    for index, chunk in enumerate(chunks):
        chunk_objects.append(
            DocumentChunk(
                document_id=document.id,
                user_id=document.user_id,
                chunk_index=index,
                content=chunk["content"],
                page_number=chunk["page_number"],
                token_count=chunk["token_count"],
            )
        )

    db.add_all(chunk_objects)

    # Update document metadata.
    if extension == ".pdf":
        document.page_count = len(extracted_pages)

    document.status = "completed"
    document.error_message = None

    await db.commit()

    return len(chunk_objects)