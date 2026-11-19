from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine
from app.routes.auth import router as auth_router
from app.routes.documents import router as documents_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        # Avoid crashing startup during offline test execution
        pass

    yield

    try:
        await engine.dispose()
    except Exception:
        pass


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(
    auth_router,
    prefix="/api/v1",
)
app.include_router(
    documents_router,
    prefix="/api/v1",
)

@app.get("/health")
async def health():
    return {
        "status": "success",
        "message": "AI Document Research Agent is running"
    }


@app.get("/health/database")
async def database_health():
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))

    return {"status": "success", "database": "connected"}