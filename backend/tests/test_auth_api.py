import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.security import verify_password
from app.main import app
from app.models.user import User


class FakeAuthQueryResult:
    def __init__(self, item=None):
        self._item = item

    def scalar_one_or_none(self):
        return self._item


class InMemoryAuthDatabaseSession:
    def __init__(self):
        self.users = {}

    def add(self, user):
        if not user.id:
            user.id = uuid.uuid4()
        self.users[user.email] = user

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def refresh(self, user):
        pass

    async def execute(self, statement):
        params = getattr(statement.compile(), "params", {})
        # Look up by email
        for val in params.values():
            if isinstance(val, str) and val in self.users:
                return FakeAuthQueryResult(self.users[val])
        # Look up by UUID id
        for val in params.values():
            if isinstance(val, uuid.UUID):
                for u in self.users.values():
                    if u.id == val:
                        return FakeAuthQueryResult(u)
        return FakeAuthQueryResult(None)


@pytest.fixture
def auth_db():
    return InMemoryAuthDatabaseSession()


@pytest.mark.asyncio
async def test_auth_register_and_login_flow(auth_db):
    app.dependency_overrides[get_db] = lambda: auth_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Register
        register_payload = {
            "full_name": "Test Researcher",
            "email": "researcher@example.com",
            "password": "StrongPassword123!",
        }
        r_reg = await client.post("/api/v1/auth/register", json=register_payload)
        assert r_reg.status_code == 201
        data_reg = r_reg.json()
        assert data_reg["email"] == "researcher@example.com"
        assert "password" not in data_reg
        assert "password_hash" not in data_reg

        # 2. Duplicate registration rejection
        r_dup = await client.post("/api/v1/auth/register", json=register_payload)
        assert r_dup.status_code == 409

        # 3. Login with wrong password
        r_fail = await client.post(
            "/api/v1/auth/login",
            json={"email": "researcher@example.com", "password": "WrongPassword"},
        )
        assert r_fail.status_code == 401

        # 4. Login with correct password
        r_login = await client.post(
            "/api/v1/auth/login",
            json={"email": "researcher@example.com", "password": "StrongPassword123!"},
        )
        assert r_login.status_code == 200
        token_data = r_login.json()
        assert "access_token" in token_data
        token = token_data["access_token"]

        # 5. Access /me
        r_me = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r_me.status_code == 200
        assert r_me.json()["email"] == "researcher@example.com"
