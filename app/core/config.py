import json
from pathlib import Path
from typing import List, Optional, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BASE_DIR / ".env"


class Settings(BaseSettings):
    PROJECT_NAME: str = "OmniSuite ERP/CRM"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    # Security
    SECRET_KEY: str = Field(default="omnisuite_super_secret_jwt_key_phase0_change_in_production_32b_min")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12  # 12 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Database
    # Standard Neon: postgresql+asyncpg://user:pass@host/dbname?ssl=require
    # Or local: sqlite+aiosqlite:///./omnisuite.db
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./omnisuite.db"
    )

    # Storage
    BLOB_READ_WRITE_TOKEN: Optional[str] = None

    # Admin Bootstrap
    ADMIN_EMAIL: str = "admin@mail.com"
    ADMIN_PASSWORD: str = "Mail@4321admin"

    # CORS
    BACKEND_CORS_ORIGINS: Union[str, List[str]] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
    ]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if not v:
            return ["*"]
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return ["*"]
            if v.startswith("[") and v.endswith("]"):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        return [str(x).strip() for x in parsed if x]
                except Exception:
                    pass
            return [x.strip() for x in v.split(",") if x.strip()]
        if isinstance(v, (list, tuple)):
            return [str(x).strip() for x in v if x]
        return ["*"]

    # Defaults
    DEFAULT_CURRENCY: str = "INR"
    DEFAULT_LOCALE: str = "en_IN"
    DEFAULT_TIMEZONE: str = "Asia/Kolkata"

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH) if ENV_PATH.exists() else ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
