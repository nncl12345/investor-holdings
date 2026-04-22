from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# `statement_cache_size=0` disables asyncpg prepared-statement caching.
# Required when running behind a transaction-mode pgbouncer (Supabase pooler,
# Heroku/Fly Postgres add-ons in some configs), which rotates the underlying
# connection between requests and invalidates server-side prepared statements.
# Tiny perf cost on direct connections; correctness everywhere else.
engine = create_async_engine(
    settings.sqlalchemy_database_url,
    echo=False,
    connect_args={"statement_cache_size": 0},
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
