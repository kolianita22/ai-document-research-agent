import io
import os
import re
import uuid
import zipfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Tuple

from fastapi import HTTPException, status

from app.core.config import settings

# Base directory for uploads: backend/uploads/documents
BASE_DIR = Path(__file__).resolve().parent.parent.parent
UPLOAD_DIR = (BASE_DIR / "uploads" / "documents").resolve()

# Allowed extensions and their expected MIME types / formats
ALLOWED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
}

# Max upload size in bytes
MAX_FILE_SIZE_BYTES = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024


class StorageProvider(ABC):
    """Abstract interface to allow interchangeable storage backends (Local, S3, Wasabi)."""

    @abstractmethod
    async def save(self, content: bytes, stored_filename: str) -> str:
        """Save file bytes and return the canonical storage path or URI."""
        pass

    @abstractmethod
    async def get(self, storage_path: str) -> bytes:
        """Retrieve file bytes by storage path or URI."""
        pass

    @abstractmethod
    async def delete(self, storage_path: str) -> bool:
        """Delete file by storage path or URI."""
        pass

    @abstractmethod
    def exists(self, storage_path: str) -> bool:
        """Check if file exists at storage path."""
        pass


class LocalStorageProvider(StorageProvider):
    """Local filesystem storage provider with path-traversal protection."""

    def __init__(self, root_dir: Path = UPLOAD_DIR):
        self.root_dir = root_dir.resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, storage_path: str) -> Path:
        target_path = Path(storage_path)
        if not target_path.is_absolute():
            target_path = (self.root_dir / target_path).resolve()
        else:
            target_path = target_path.resolve()

        # Prevent directory traversal attacks
        try:
            target_path.relative_to(self.root_dir)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid storage path: directory traversal detected",
            )
        return target_path

    async def save(self, content: bytes, stored_filename: str) -> str:
        target_path = self._resolve_safe_path(stored_filename)

        if target_path.exists():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A file with this storage identifier already exists",
            )

        # Write to disk
        target_path.write_bytes(content)
        return str(target_path)

    async def get(self, storage_path: str) -> bytes:
        target_path = self._resolve_safe_path(storage_path)
        if not target_path.exists() or not target_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Stored file not found on disk",
            )
        return target_path.read_bytes()

    async def delete(self, storage_path: str) -> bool:
        try:
            target_path = self._resolve_safe_path(storage_path)
            if target_path.exists() and target_path.is_file():
                target_path.unlink()
                return True
            return False
        except Exception:
            return False

    def exists(self, storage_path: str) -> bool:
        try:
            target_path = self._resolve_safe_path(storage_path)
            return target_path.exists() and target_path.is_file()
        except Exception:
            return False


class DocumentStorageService:
    """High-level document storage manager providing validation, sanitization, and lifecycle methods."""

    def __init__(self, provider: StorageProvider = None):
        self.provider = provider or LocalStorageProvider()

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitizes user-supplied filenames to prevent path traversal and control character issues."""
        if not filename:
            return "untitled"
        # Extract basename only
        clean_name = os.path.basename(filename.strip())
        # Replace dangerous or whitespace characters
        clean_name = re.sub(r"[^\w\s\.-]", "_", clean_name)
        return clean_name or "untitled"

    def validate_file(self, filename: str, content: bytes) -> Tuple[str, str]:
        """
        Validates file extension, size, and actual magic bytes / internal structure.
        Returns:
            Tuple[clean_extension, detected_file_type]
        Raises:
            HTTPException on validation failure
        """
        # 1. Check for empty file
        if not content or len(content) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty (0 bytes)",
            )

        # 2. Check maximum size
        if len(content) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"File size exceeds maximum allowed limit of {settings.MAX_UPLOAD_SIZE_MB}MB",
            )

        # 3. Validate extension
        sanitized = self.sanitize_filename(filename)
        ext = os.path.splitext(sanitized)[1].lower()

        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file format '{ext}'. Allowed formats are: {', '.join(ALLOWED_EXTENSIONS.keys())}",
            )

        # 4. Deep content validation (magic bytes & file headers)
        if ext == ".pdf":
            # PDF header check: %PDF-
            if not content.startswith(b"%PDF-"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid PDF file: corrupted or missing %PDF- header",
                )
            file_type = "pdf"

        elif ext == ".docx":
            # DOCX is a zip archive with 'word/document.xml' or '[Content_Types].xml'
            if not content.startswith(b"PK\x03\x04"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid DOCX file: missing ZIP header signature",
                )
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    namelist = zf.namelist()
                    if not any("word/document.xml" in name or "[Content_Types].xml" in name for name in namelist):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid DOCX file: missing Word document structure",
                        )
            except zipfile.BadZipFile:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid DOCX file: corrupted archive",
                )
            file_type = "docx"

        elif ext == ".txt":
            # TXT should not contain binary null bytes and must decode cleanly
            if b"\x00" in content:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid text file: binary content or null bytes detected",
                )
            try:
                content.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    content.decode("latin-1")
                except Exception:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid text file: unreadable encoding",
                    )
            file_type = "txt"

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file format: {ext}",
            )

        return ext, file_type

    async def save_file(self, filename: str, content: bytes) -> Tuple[str, str, str]:
        """
        Validates, generates unique UUID filename, and writes file to storage.
        Returns:
            Tuple[stored_filename, storage_path, file_type]
        """
        ext, file_type = self.validate_file(filename, content)
        stored_filename = f"{uuid.uuid4().hex}{ext}"
        storage_path = await self.provider.save(content, stored_filename)
        return stored_filename, storage_path, file_type

    async def delete_file(self, storage_path: str) -> bool:
        """Deletes file from storage."""
        return await self.provider.delete(storage_path)


# Singleton storage service
storage_service = DocumentStorageService()
