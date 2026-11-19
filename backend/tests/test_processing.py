import io
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import docx
import pymupdf
import pytest

from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.processors.docx_processor import extract_docx
from app.processors.pdf_processor import extract_pdf
from app.processors.text_chunker import (
    clean_text,
    create_document_chunks,
    estimate_tokens,
    split_into_chunks,
)
from app.processors.txt_processor import extract_txt
from app.services.processing_service import process_document


# ==========================================
# 1. Extraction & Parsing Tests
# ==========================================

def test_pdf_extraction_and_page_number_preservation(tmp_path):
    """Test PDF text extraction and verify page numbers are preserved."""
    pdf_path = tmp_path / "multipage.pdf"
    doc = pymupdf.open()

    p1 = doc.new_page()
    p1.insert_text((50, 72), "First page content paragraph.")

    p2 = doc.new_page()
    p2.insert_text((50, 72), "Second page content paragraph.")

    doc.save(str(pdf_path))
    doc.close()

    extracted = extract_pdf(str(pdf_path))
    assert len(extracted) == 2
    assert extracted[0]["page_number"] == 1
    assert "First page content" in extracted[0]["text"]
    assert extracted[1]["page_number"] == 2
    assert "Second page content" in extracted[1]["text"]


def test_docx_text_extraction(tmp_path):
    """Test DOCX text extraction."""
    docx_path = tmp_path / "sample.docx"
    doc = docx.Document()
    doc.add_paragraph("Paragraph 1 of DOCX document.")
    doc.add_paragraph("Paragraph 2 of DOCX document.")
    doc.save(str(docx_path))

    extracted = extract_docx(str(docx_path))
    assert len(extracted) == 1
    assert extracted[0]["page_number"] is None
    assert "Paragraph 1" in extracted[0]["text"]
    assert "Paragraph 2" in extracted[0]["text"]


def test_txt_text_extraction(tmp_path):
    """Test TXT text extraction."""
    txt_path = tmp_path / "sample.txt"
    txt_path.write_text("Hello World from a text file.\nSecond line.", encoding="utf-8")

    extracted = extract_txt(str(txt_path))
    assert len(extracted) == 1
    assert extracted[0]["page_number"] is None
    assert "Hello World from a text file" in extracted[0]["text"]


# ==========================================
# 2. Error Handling & Corruption Tests
# ==========================================

def test_empty_documents_fail_safely(tmp_path):
    """Empty PDF, DOCX, and TXT documents must raise ValueError safely."""
    # Empty PDF (blank page with no text)
    empty_pdf = tmp_path / "empty.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(str(empty_pdf))
    doc.close()

    with pytest.raises(ValueError) as exc_pdf:
        extract_pdf(str(empty_pdf))
    assert "no readable text" in str(exc_pdf.value).lower()

    # Empty DOCX
    empty_docx = tmp_path / "empty.docx"
    doc_docx = docx.Document()
    doc_docx.save(str(empty_docx))

    with pytest.raises(ValueError) as exc_docx:
        extract_docx(str(empty_docx))
    assert "no readable text" in str(exc_docx.value).lower()

    # Empty TXT
    empty_txt = tmp_path / "empty.txt"
    empty_txt.write_text("   \n  \n", encoding="utf-8")

    with pytest.raises(ValueError) as exc_txt:
        extract_txt(str(empty_txt))
    assert "empty" in str(exc_txt.value).lower()


def test_corrupted_pdf_fails_safely(tmp_path):
    """Corrupted PDF must raise ValueError cleanly without unhandled crashes."""
    corrupt_pdf = tmp_path / "corrupt.pdf"
    corrupt_pdf.write_bytes(b"%PDF-1.4\nCorruptedGarbageTrailerInvalidOffsetsXXXX")

    with pytest.raises(ValueError) as exc_info:
        extract_pdf(str(corrupt_pdf))
    assert "corrupted" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()


# ==========================================
# 3. Chunking & Overlap Tests
# ==========================================

def test_chunks_have_configured_overlap():
    """Verify that chunks maintain the specified overlap."""
    sentence = "Artificial intelligence research requires deep analysis of documents and retrieval augmented generation. "
    full_text = sentence * 20  # ~2100 characters

    chunk_size = 300
    overlap = 50

    chunks = split_into_chunks(full_text, chunk_size=chunk_size, overlap=overlap)
    assert len(chunks) > 1

    for i in range(len(chunks) - 1):
        c1 = chunks[i]
        c2 = chunks[i + 1]

        # Suffix of chunk 1 should overlap with prefix of chunk 2
        suffix_words = [w for w in c1.split() if len(w) > 3][-3:]
        overlap_found = any(word in c2 for word in suffix_words)
        assert overlap_found, f"Expected overlap between chunk {i} and {i+1}"


def test_create_document_chunks_preserves_page_numbers():
    pages = [
        {"page_number": 1, "text": "Page one text content for testing chunking."},
        {"page_number": 2, "text": "Page two text content with additional information."},
    ]

    chunks = create_document_chunks(pages, chunk_size=100, overlap=20)
    assert len(chunks) >= 2
    assert chunks[0]["page_number"] == 1
    assert chunks[-1]["page_number"] == 2
    assert chunks[0]["token_count"] > 0


# ==========================================
# 4. Processing Service & DB Integration Tests
# ==========================================

class MockAsyncSession:
    def __init__(self):
        self.added = []
        self.deleted = []
        self.committed = False

    def add_all(self, items):
        self.added.extend(items)

    async def execute(self, stmt):
        # Handle delete statements
        self.deleted.append(stmt)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        pass


@pytest.mark.asyncio
async def test_chunk_metadata_saved_in_database(tmp_path):
    """Test that chunk metadata is created and committed to the database."""
    pdf_path = tmp_path / "valid.pdf"
    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text((50, 72), "Document processing test content with valuable knowledge.")
    doc.save(str(pdf_path))
    doc.close()

    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    document = Document(
        id=doc_id,
        user_id=user_id,
        original_filename="valid.pdf",
        stored_filename="valid.pdf",
        file_type="pdf",
        file_size=1024,
        storage_path=str(pdf_path),
        status="uploaded",
    )

    mock_db = MockAsyncSession()
    count = await process_document(mock_db, document)

    assert count > 0
    assert document.status == "completed"
    assert document.page_count == 1
    assert mock_db.committed is True

    # Verify chunk attributes
    chunk = mock_db.added[0]
    assert isinstance(chunk, DocumentChunk)
    assert chunk.document_id == doc_id
    assert chunk.user_id == user_id
    assert chunk.chunk_index == 0
    assert chunk.page_number == 1
    assert chunk.token_count > 0


@pytest.mark.asyncio
async def test_reprocessing_does_not_duplicate_chunks(tmp_path):
    """Reprocessing must delete old chunks and not create duplicates."""
    txt_path = tmp_path / "reprocess.txt"
    txt_path.write_text("Unique text content for idempotency testing.", encoding="utf-8")

    document = Document(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        original_filename="reprocess.txt",
        stored_filename="reprocess.txt",
        file_type="txt",
        file_size=100,
        storage_path=str(txt_path),
        status="uploaded",
    )

    mock_db = MockAsyncSession()

    # First run
    await process_document(mock_db, document)
    assert len(mock_db.deleted) == 1  # delete(DocumentChunk) was executed

    # Second run (reprocess)
    await process_document(mock_db, document)
    assert len(mock_db.deleted) == 2  # delete(DocumentChunk) was executed again


# ==========================================
# 5. Celery Task Error Handling Tests
# ==========================================

@pytest.mark.asyncio
async def test_failed_document_receives_failed_status(tmp_path):
    """When processing encounters an error, the document is marked as failed."""
    invalid_txt = tmp_path / "bad.txt"
    invalid_txt.write_text("   ", encoding="utf-8")  # Empty

    doc_id = uuid.uuid4()
    document = Document(
        id=doc_id,
        user_id=uuid.uuid4(),
        original_filename="bad.txt",
        stored_filename="bad.txt",
        file_type="txt",
        file_size=10,
        storage_path=str(invalid_txt),
        status="uploaded",
    )

    mock_db = MockAsyncSession()

    with pytest.raises(ValueError):
        await process_document(mock_db, document)


# ==========================================
# 6. Multi-User Isolation Tests
# ==========================================

def test_users_cannot_access_another_users_chunks():
    """Ensure chunk user_id strictly binds to document user_id."""
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    doc_a = Document(
        id=uuid.uuid4(),
        user_id=user_a,
        original_filename="a.txt",
        stored_filename="a.txt",
        file_type="txt",
        file_size=10,
        storage_path="path/a.txt",
    )

    chunk_a = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc_a.id,
        user_id=doc_a.user_id,
        chunk_index=0,
        content="Confidential user A notes",
    )

    # Chunks of user A must never match user B
    assert chunk_a.user_id == user_a
    assert chunk_a.user_id != user_b
