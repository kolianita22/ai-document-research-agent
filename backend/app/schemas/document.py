import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class DocumentUploadResponse(BaseModel):
    id: uuid.UUID
    original_filename: str
    file_type: str
    file_size: int
    status: str
    created_at: datetime
    message: str = "Document uploaded successfully"

    model_config = ConfigDict(from_attributes=True)


class DocumentDetailResponse(BaseModel):
    id: uuid.UUID
    original_filename: str
    file_type: str
    file_size: int
    page_count: Optional[int] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    processed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DocumentListResponse(BaseModel):
    items: List[DocumentDetailResponse]
    total: int
    page: int
    page_size: int

    model_config = ConfigDict(from_attributes=True)


class DocumentStatusResponse(BaseModel):
    id: uuid.UUID
    status: str
    page_count: Optional[int] = None
    error_message: Optional[str] = None
    processed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
