from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    APP_NAME: str = "AI Document Research Agent"
    APP_ENV: str = "development"
    DEBUG: bool = True

    DATABASE_URL: str
    REDIS_URL: str

    QDRANT_URL: str
    QDRANT_COLLECTION: str = "document_chunks"
    QDRANT_VECTOR_SIZE: int = 1536

    OPENAI_API_KEY: str = ""
    OPENAI_CHAT_MODEL: str = ""
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    MAX_UPLOAD_SIZE_MB: int = 20

    model_config = SettingsConfigDict(
        env_file=(
            str(BASE_DIR.parent / ".env"),
            str(BASE_DIR / ".env"),
            ".env",
            "../.env",
        ),
        extra="ignore"
    )


settings = Settings()