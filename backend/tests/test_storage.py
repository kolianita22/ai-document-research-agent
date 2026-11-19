import io
import os
import pytest
from fastapi import HTTPException

import docx
import pymupdf
from app.services.storage import DocumentStorageService, LocalStorageProvider, MAX_FILE_SIZE_BYTES


@pytest.fixture
def storage_service(tmp_path):
    provider = LocalStorageProvider(root_dir=tmp_path)
    return DocumentStorageService(provider=provider)


@pytest.fixture
def sample_pdf():
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), "Sample PDF text for unit test")
    return doc.tobytes()


@pytest.fixture
def sample_docx():
    doc = docx.Document()
    doc.add_paragraph("Sample Word document for unit test")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.fixture
def sample_txt():
    return "This is a clean UTF-8 text file content.".encode("utf-8")


@pytest.mark.asyncio
async def test_save_valid_pdf(storage_service, sample_pdf):
    stored_name, path, ftype = await storage_service.save_file("report.pdf", sample_pdf)
    assert ftype == "pdf"
    assert stored_name.endswith(".pdf")
    assert os.path.exists(path)
    assert await storage_service.delete_file(path) is True


@pytest.mark.asyncio
async def test_save_valid_docx(storage_service, sample_docx):
    stored_name, path, ftype = await storage_service.save_file("analysis.docx", sample_docx)
    assert ftype == "docx"
    assert stored_name.endswith(".docx")
    assert os.path.exists(path)
    assert await storage_service.delete_file(path) is True


@pytest.mark.asyncio
async def test_save_valid_txt(storage_service, sample_txt):
    stored_name, path, ftype = await storage_service.save_file("notes.txt", sample_txt)
    assert ftype == "txt"
    assert stored_name.endswith(".txt")
    assert os.path.exists(path)
    assert await storage_service.delete_file(path) is True


@pytest.mark.asyncio
async def test_reject_empty_file(storage_service):
    with pytest.raises(HTTPException) as exc_info:
        await storage_service.save_file("empty.txt", b"")
    assert exc_info.value.status_code == 400
    assert "empty" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_reject_oversized_file(storage_service):
    oversized_data = b"A" * (MAX_FILE_SIZE_BYTES + 1024)
    with pytest.raises(HTTPException) as exc_info:
        await storage_service.save_file("big.txt", oversized_data)
    assert exc_info.value.status_code == 413


@pytest.mark.asyncio
async def test_reject_unsupported_extension(storage_service):
    with pytest.raises(HTTPException) as exc_info:
        await storage_service.save_file("malicious.exe", b"fake binary data")
    assert exc_info.value.status_code == 400
    assert "unsupported" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_reject_fake_pdf(storage_service):
    fake_pdf = b"NOT_A_REAL_PDF_CONTENT"
    with pytest.raises(HTTPException) as exc_info:
        await storage_service.save_file("fake.pdf", fake_pdf)
    assert exc_info.value.status_code == 400
    assert "pdf" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_reject_fake_docx(storage_service):
    fake_docx = b"PK\x03\x04INVALID_ZIP_CONTENT_HERE"
    with pytest.raises(HTTPException) as exc_info:
        await storage_service.save_file("fake.docx", fake_docx)
    assert exc_info.value.status_code == 400
    assert "docx" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_reject_binary_txt(storage_service):
    binary_txt = b"Text with null \x00 byte inside"
    with pytest.raises(HTTPException) as exc_info:
        await storage_service.save_file("binary.txt", binary_txt)
    assert exc_info.value.status_code == 400
    assert "null bytes" in exc_info.value.detail.lower()


def test_sanitize_filename(storage_service):
    assert storage_service.sanitize_filename("../../etc/passwd.txt") == "passwd.txt"
    assert storage_service.sanitize_filename("folder/subfolder/my-file.pdf") == "my-file.pdf"
    assert storage_service.sanitize_filename("valid_name-1.0.docx") == "valid_name-1.0.docx"
