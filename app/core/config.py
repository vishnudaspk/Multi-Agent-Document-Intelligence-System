"""
app/core/config.py
Central settings — all values read from environment / .env file.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── App ────────────────────────────────────────────────────
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    upload_dir: str = "data/uploads"
    processed_dir: str = "data/processed"

    # ── Database ───────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://madis_user:madis_pass@localhost:5432/madis_db"
    postgres_user: str = "madis_user"
    postgres_password: str = "madis_pass"
    postgres_db: str = "madis_db"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # ── Redis / Celery ─────────────────────────────────────────
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # ── Qdrant ────────────────────────────────────────────────
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_grpc_port: int = 6334
    qdrant_collection_name: str = "documents"

    # ── LLM ───────────────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2:7b-instruct-q4_K_M"
    lmstudio_base_url: str = ""        # set to use LMStudio instead
    lmstudio_api_key: str = "lm-studio"

    # ── Embeddings ────────────────────────────────────────────
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # ── MLflow ────────────────────────────────────────────────
    mlflow_tracking_uri: str = "http://localhost:5000"

    @property
    def llm_base_url(self) -> str:
        """Returns whichever LLM backend is configured."""
        return self.lmstudio_base_url or self.ollama_base_url

    @property
    def llm_api_key(self) -> str:
        return self.lmstudio_api_key if self.lmstudio_base_url else "ollama"

    @property
    def llm_model(self) -> str:
        return self.ollama_model  # same model name works for both backends


settings = Settings()
