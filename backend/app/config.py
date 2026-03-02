import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

VLLM_BASE_URL: str = os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
VLLM_MODEL: str = os.getenv("VLLM_MODEL", "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B")

API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
API_PORT: int = int(os.getenv("API_PORT", "8080"))

POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB: str = os.getenv("POSTGRES_DB", "spreadsheet_analysis")
POSTGRES_USER: str = os.getenv("POSTGRES_USER", "sa_user")
POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "changeme")

REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))

DATA_DIR: Path = Path(os.getenv("DATA_DIR", "./data")).resolve()
UPLOAD_MAX_SIZE_MB: int = int(os.getenv("UPLOAD_MAX_SIZE_MB", "50"))

SANDBOX_TIMEOUT_SECONDS: int = int(os.getenv("SANDBOX_TIMEOUT_SECONDS", "30"))
SANDBOX_MAX_RETRIES: int = int(os.getenv("SANDBOX_MAX_RETRIES", "2"))


def database_url() -> str:
    return (
        f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )
