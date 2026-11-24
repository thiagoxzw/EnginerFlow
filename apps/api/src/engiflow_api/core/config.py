"""Configuração da aplicação, lida de variáveis de ambiente (prefixo ENGIFLOW_)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ENGIFLOW_", env_file=".env", extra="ignore")

    database_url: str = Field(
        default="postgresql+psycopg://engiflow:engiflow@127.0.0.1:5432/engiflow",
        description="URL SQLAlchemy. PostgreSQL em produção local; SQLite só em testes unitários.",
    )
    session_ttl_hours: int = Field(default=12, ge=1, le=168)
    cookie_secure: bool = Field(
        default=False,
        description="Marca o cookie como Secure. Ative se servido por HTTPS.",
    )
    frontend_origin: str = Field(default="http://127.0.0.1:3000")
    log_level: str = Field(default="INFO")
    data_dir: str = Field(
        default="data",
        description="Pasta dos arquivos originais importados. Fora do Git (ADR-0011).",
    )
    max_upload_mb: int = Field(default=100, ge=1, le=1024)
    max_rows: int = Field(default=500_000, ge=1)
    app_version: str = Field(default="0.1.0")


@lru_cache
def get_settings() -> Settings:
    return Settings()
