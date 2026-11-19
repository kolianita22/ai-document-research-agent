import io
import uuid
from datetime import datetime, timezone

import docx
import pymupdf
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.security import create_access_token
from app.main import app
from app.models.document import Document, DocumentStatus
from app.models.user import User


class FakeQueryResult:
    def __init__(self, items=None, scalar_val=None):
        self._items = items or []
        self._scalar_val = scalar_val

    def scalar_one_or_none(self):
        return self._items[0] if self._items else None

    def scalars(self):
        class ScalarList:
            def __init__(self, items):
                self._items = items

            def all(self):
                return self._items

        return ScalarList(self._items)

    def scalar(self):
        return self._scalar_val


class InMemoryDatabaseSession:
    def __init__(self):
        self.documents = {}
        self.users = {}

    def add(self, obj):
        now = datetime.now(timezone.utc)
        if isinstance(obj, Document):
            if not obj.id:
                obj.id = uuid.uuid4()
            if not obj.created_at:
                obj.created_at = now
            if not obj.updated_at:
                obj.updated_at = now
            self.documents[obj.id] = obj
        elif isinstance(obj, User):
            if not obj.id:
                obj.id = uuid.uuid4()
            self.users[obj.id] = obj

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def refresh(self, obj):
        pass

    async def delete(self, obj):
        if isinstance(obj, Document):
            self.documents.pop(obj.id, None)

    async def execute(self, statement):
        params = getattr(statement.compile(), "params", {})

        # Check if looking up a specific document by its UUID in params
        for val in params.values():
            if isinstance(val, uuid.UUID) and val in self.documents:
                return FakeQueryResult([self.documents[val]])

        sql = str(statement)

        # Check if query is targeting User
        if "FROM users" in sql:
            for val in params.values():
                if isinstance(val, uuid.UUID) and val in self.users:
                    return FakeQueryResult([self.users[val]])
            if len(self.users) == 1:
                return FakeQueryResult(list(self.users.values()))
            return FakeQueryResult([])

        # Check if count query
        if "select count(" in sql.lower():
            user_id = next((v for v in params.values() if isinstance(v, uuid.UUID) and v in self.users), None)
            if user_id:
                count = sum(1 for d in self.documents.values() if d.user_id == user_id and d.status != DocumentStatus.DELETING)
            else:
                count = sum(1 for d in self.documents.values() if d.status != DocumentStatus.DELETING)
            return FakeQueryResult([], scalar_val=count)

        # List documents (optionally filtered by user)
        user_id = next((v for v in params.values() if isinstance(v, uuid.UUID) and v in self.users), None)
        if user_id:
            docs = [d for d in self.documents.values() if d.user_id == user_id and d.status != DocumentStatus.DELETING]
        else:
            docs = [d for d in self.documents.values() if d.status != DocumentStatus.DELETING]

        docs.sort(key=lambda d: d.created_at, reverse=True)
        return FakeQueryResult(docs)


@pytest.fixture
def fake_db():
    return InMemoryDatabaseSession()


@pytest.fixture
def user_a(fake_db):
    user = User(
        id=uuid.uuid4(),
        email="user_a@example.com",
        full_name="User A",
        password_hash="hash",
        is_active=True,
    )
    fake_db.add(user)
    return user


@pytest.fixture
def user_b(fake_db):
    user = User(
        id=uuid.uuid4(),
        email="user_b@example.com",
        full_name="User B",
        password_hash="hash",
        is_active=True,
    )
    fake_db.add(user)
    return user


@pytest.fixture
def auth_headers_user_a(user_a):
    token = create_access_token(str(user_a.id))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_user_b(user_b):
    token = create_access_token(str(user_b.id))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_pdf_bytes():
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), "AI Document Research Agent Test PDF")
    return doc.tobytes()


@pytest.fixture
def sample_docx_bytes():
    doc = docx.Document()
    doc.add_paragraph("AI Document Research Agent Test DOCX")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.fixture
def sample_txt_bytes():
    return "AI Document Research Agent Test TXT Content".encode("utf-8")


@pytest.mark.asyncio
async def test_unauthenticated_requests():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r1 = await client.get("/api/v1/documents/")
        assert r1.status_code == 403 or r1.status_code == 401

        r2 = await client.post("/api/v1/documents/upload")
        assert r2.status_code == 403 or r2.status_code == 401


@pytest.mark.asyncio
async def test_invalid_jwt_token():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": "Bearer invalid_malformed_jwt"}
        response = await client.get("/api/v1/documents/", headers=headers)
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_upload_valid_pdf(fake_db, user_a, auth_headers_user_a, sample_pdf_bytes):
    app.dependency_overrides[get_db] = lambda: fake_db
    app.dependency_overrides[get_current_user] = lambda: user_a

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        files = {"file": ("report.pdf", sample_pdf_bytes, "application/pdf")}
        response = await client.post(
            "/api/v1/documents/upload",
            headers=auth_headers_user_a,
            files=files,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["original_filename"] == "report.pdf"
        assert data["file_type"] == "pdf"
        assert data["status"] == "uploaded"
        assert "storage_path" not in data  # Path must never be exposed


@pytest.mark.asyncio
async def test_upload_valid_docx(fake_db, user_a, auth_headers_user_a, sample_docx_bytes):
    app.dependency_overrides[get_db] = lambda: fake_db
    app.dependency_overrides[get_current_user] = lambda: user_a

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        files = {"file": ("thesis.docx", sample_docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        response = await client.post(
            "/api/v1/documents/upload",
            headers=auth_headers_user_a,
            files=files,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["original_filename"] == "thesis.docx"
        assert data["file_type"] == "docx"
        assert data["status"] == "uploaded"


@pytest.mark.asyncio
async def test_upload_valid_txt(fake_db, user_a, auth_headers_user_a, sample_txt_bytes):
    app.dependency_overrides[get_db] = lambda: fake_db
    app.dependency_overrides[get_current_user] = lambda: user_a

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        files = {"file": ("notes.txt", sample_txt_bytes, "text/plain")}
        response = await client.post(
            "/api/v1/documents/upload",
            headers=auth_headers_user_a,
            files=files,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["original_filename"] == "notes.txt"
        assert data["file_type"] == "txt"


@pytest.mark.asyncio
async def test_upload_unsupported_file_rejection(fake_db, user_a, auth_headers_user_a):
    app.dependency_overrides[get_db] = lambda: fake_db
    app.dependency_overrides[get_current_user] = lambda: user_a

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        files = {"file": ("virus.exe", b"MZ\x90\x00BinaryContent", "application/octet-stream")}
        response = await client.post(
            "/api/v1/documents/upload",
            headers=auth_headers_user_a,
            files=files,
        )
        assert response.status_code == 400
        assert "unsupported" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_upload_empty_file_rejection(fake_db, user_a, auth_headers_user_a):
    app.dependency_overrides[get_db] = lambda: fake_db
    app.dependency_overrides[get_current_user] = lambda: user_a

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        files = {"file": ("empty.txt", b"", "text/plain")}
        response = await client.post(
            "/api/v1/documents/upload",
            headers=auth_headers_user_a,
            files=files,
        )
        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_upload_duplicate_filenames(fake_db, user_a, auth_headers_user_a, sample_txt_bytes):
    app.dependency_overrides[get_db] = lambda: fake_db
    app.dependency_overrides[get_current_user] = lambda: user_a

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        files1 = {"file": ("document.txt", sample_txt_bytes, "text/plain")}
        r1 = await client.post("/api/v1/documents/upload", headers=auth_headers_user_a, files=files1)
        assert r1.status_code == 201
        id1 = r1.json()["id"]

        files2 = {"file": ("document.txt", sample_txt_bytes, "text/plain")}
        r2 = await client.post("/api/v1/documents/upload", headers=auth_headers_user_a, files=files2)
        assert r2.status_code == 201
        id2 = r2.json()["id"]

        # IDs must be different and stored safely without conflict
        assert id1 != id2


@pytest.mark.asyncio
async def test_list_and_detail_documents(fake_db, user_a, auth_headers_user_a, sample_txt_bytes):
    app.dependency_overrides[get_db] = lambda: fake_db
    app.dependency_overrides[get_current_user] = lambda: user_a

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Upload one doc
        files = {"file": ("list_test.txt", sample_txt_bytes, "text/plain")}
        r_up = await client.post("/api/v1/documents/upload", headers=auth_headers_user_a, files=files)
        doc_id = r_up.json()["id"]

        # List
        r_list = await client.get("/api/v1/documents/", headers=auth_headers_user_a)
        assert r_list.status_code == 200
        list_data = r_list.json()
        print("DEBUG LIST_DATA:", list_data)
        assert list_data["total"] >= 1
        assert any(item["id"] == doc_id for item in list_data["items"])

        # Detail
        r_detail = await client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers_user_a)
        assert r_detail.status_code == 200
        assert r_detail.json()["id"] == doc_id
        assert "storage_path" not in r_detail.json()

        # Status
        r_status = await client.get(f"/api/v1/documents/{doc_id}/status", headers=auth_headers_user_a)
        assert r_status.status_code == 200
        assert r_status.json()["status"] == "uploaded"


@pytest.mark.asyncio
async def test_delete_and_reprocess_document(fake_db, user_a, auth_headers_user_a, sample_txt_bytes):
    app.dependency_overrides[get_db] = lambda: fake_db
    app.dependency_overrides[get_current_user] = lambda: user_a

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        files = {"file": ("to_delete.txt", sample_txt_bytes, "text/plain")}
        r_up = await client.post("/api/v1/documents/upload", headers=auth_headers_user_a, files=files)
        doc_id = r_up.json()["id"]

        # Reprocess
        r_re = await client.post(f"/api/v1/documents/{doc_id}/reprocess", headers=auth_headers_user_a)
        assert r_re.status_code == 200
        assert r_re.json()["status"] == "uploaded"

        # Delete
        r_del = await client.delete(f"/api/v1/documents/{doc_id}", headers=auth_headers_user_a)
        assert r_del.status_code == 200

        # Attempt to get deleted document
        r_get = await client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers_user_a)
        assert r_get.status_code == 404


@pytest.mark.asyncio
async def test_unauthorized_cross_user_access(fake_db, user_a, user_b, auth_headers_user_a, auth_headers_user_b, sample_txt_bytes):
    # Upload document as User A
    app.dependency_overrides[get_db] = lambda: fake_db
    app.dependency_overrides[get_current_user] = lambda: user_a

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        files = {"file": ("user_a_private.txt", sample_txt_bytes, "text/plain")}
        r_up = await client.post("/api/v1/documents/upload", headers=auth_headers_user_a, files=files)
        doc_id = r_up.json()["id"]

        # Switch authentication to User B
        app.dependency_overrides[get_current_user] = lambda: user_b

        # User B attempts to access User A's document
        r_forbidden = await client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers_user_b)
        assert r_forbidden.status_code == 403
        assert "access denied" in r_forbidden.json()["detail"].lower()

        # User B attempts to delete User A's document
        r_del_forbidden = await client.delete(f"/api/v1/documents/{doc_id}", headers=auth_headers_user_b)
        assert r_del_forbidden.status_code == 403

        # User B attempts to reprocess User A's document
        r_rep_forbidden = await client.post(f"/api/v1/documents/{doc_id}/reprocess", headers=auth_headers_user_b)
        assert r_rep_forbidden.status_code == 403
