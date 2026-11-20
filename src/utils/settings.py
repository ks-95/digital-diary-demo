from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            str(BASE_DIR / ".env"),
            str(BASE_DIR.parent / ".env"),
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DB_CONNECTION: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/digital_diary"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: float = 30.0
    DB_SSL: bool = False
    ENVIRONMENT: str = "development"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5000,http://localhost:8000"
    STORAGE_BACKEND: str = "local"
    EVIDENCE_STORAGE_DIR: str = "storage/evidence"
    SUPABASE_URL: str = ""
    SUPABASE_SECRET_KEY: str = ""
    # Legacy key name retained for existing deployments during key migration.
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_STORAGE_BUCKET: str = "case-files"
    OLLAMA_HOST: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1:8b"
    OLLAMA_VISION_MODEL: str = "minicpm-v:latest"
    JWT_SECRET_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.8-flash"  # change in .env if Google renames the model
    AI_PROVIDER: str = "auto"  # auto = Gemini first, OpenAI on transient Gemini capacity errors
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-5.5"
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""
    RAZORPAY_PLAN_ID: str = ""
    RAZORPAY_TOTAL_COUNT: int = 120
    BILLING_ENFORCED: bool = False
    AUTO_INIT_DB: bool = True


settings = Settings()
