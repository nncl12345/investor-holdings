from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://holdings:holdings@localhost:5432/holdings"
    redis_url: str = "redis://localhost:6379/0"

    # SEC EDGAR requires a descriptive User-Agent header identifying your app/contact
    # See: https://www.sec.gov/developer
    edgar_user_agent: str = "investor-holdings-app contact@example.com"
    edgar_base_url: str = "https://efts.sec.gov/LATEST/search-index"
    edgar_submissions_url: str = "https://data.sec.gov/submissions"

    groq_api_key: str = ""
    tavily_api_key: str = ""

    # Comma-separated list of origins allowed to call the API from a browser.
    # In production set to e.g. "https://holdings.example.com".
    # "*" is fine for a public read-only demo but disables cookie-bearing requests.
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Shared secret for write endpoints (POST /investors, POST /investors/{id}/sync).
    # If empty, write endpoints are unprotected (local-dev default).
    api_key: str = ""

    @property
    def sqlalchemy_database_url(self) -> str:
        """
        Normalize DATABASE_URL for async SQLAlchemy.

        Managed Postgres providers (Fly, Heroku, Render) hand you a URL like
        `postgres://user:pass@host/db`. SQLAlchemy async needs
        `postgresql+asyncpg://...`. This converts transparently so the same
        env var works locally and in prod.
        """
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://") and "+asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


settings = Settings()
