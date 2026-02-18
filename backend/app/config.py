from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

# Default SQLite path for development (no Docker needed)
_DEFAULT_DB = f"sqlite:///{Path(__file__).resolve().parent.parent / 'woodworking.db'}"


class Settings(BaseSettings):
    # Database — defaults to SQLite for dev; use PostgreSQL in production
    database_url: str = _DEFAULT_DB

    # Auth
    jwt_secret_key: str = "change-me-to-a-long-random-string-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 480

    # Backend
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    engine_version: str = "2.0.0"

    # ML
    ml_model_path: str = "./models/ml_adjuster/catboost_model.cbm"
    ml_enabled: bool = False

    # PDF
    pdf_company_name: str = "B10 Union, LLC"
    pdf_company_address: str = "Atlanta, GA"
    pdf_company_phone: str = ""
    pdf_company_email: str = ""

    # Rounding
    rounding_mode: str = "ROUND_HALF_UP"
    rounding_places: int = 2

    # Vision
    anthropic_api_key: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
