import os
from typing import Tuple

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

env = os.getenv("ENV", "dev")
load_dotenv(f".env.{env}", override=False)


class Settings(BaseSettings):
    PROJECT_NAME: str = "elbiefit"
    REGION: str = "eu-west-2"
    ENV: str = "dev"
    DDB_TABLE_NAME: str = "elbiefit-dev-table"
    DDB_ENDPOINT_URL: str | None = None
    model_config = SettingsConfigDict(env_file=None)

    # ──────────────────── Auth ─────────────────────

    DISABLE_AUTH_FOR_LOCAL_DEV: bool = False
    DEV_USER_SUB: str | None = None

    COGNITO_AUDIENCE: str = ""
    COGNITO_DOMAIN: str = ""
    COGNITO_REDIRECT_URI: str = ""
    COGNITO_ISSUER_URL: str = ""

    # ──────────────────── Rate limiting ─────────────────────
    RATE_LIMIT_ENABLED: bool = True

    RATE_LIMIT_READ_PER_MIN: int = 120
    RATE_LIMIT_WRITE_PER_MIN: int = 30

    RATE_LIMIT_TTL_SECONDS: int = 600

    # Prefixes that should never be rate limited
    RATE_LIMIT_EXCLUDED_PREFIXES: tuple[str, ...] = (
        "/static",
        "/favicon.ico",
        "/robots.txt",
        "/health",
        "/meta",
    )
    # ──────────────────── CSRF ─────────────────────
    CSRF_ENABLED: bool = True
    CSRF_EXCLUDED_PREFIXES: Tuple[str, ...] = (
        "/static",
        "/favicon.ico",
        "/robots.txt",
        "/healthz",
        "/meta",
        "/auth",
    )

    # ──────────────────── Theme ─────────────────────
    DEFAULT_THEME: str = "prehistoric"
    THEMES: Tuple[str, ...] = ("apothecary", "ink", "prehistoric")
    THEME_EXCLUDED_PREFIXES: Tuple[str, ...] = ("/static",)

    # ─────────────────────────────────────────

    def cognito_base_url(self) -> str:
        return f"https://{self.COGNITO_DOMAIN}.auth.{self.REGION}.amazoncognito.com"

    def auth_url(self) -> str:
        return f"{self.cognito_base_url()}/oauth2/authorize"

    def token_url(self) -> str:
        return f"{self.cognito_base_url()}/oauth2/token"


settings = Settings()
