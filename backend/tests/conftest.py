"""
Shared test fixtures. We spin up an in-memory async SQLite DB per test so
tests are isolated, fast, and don't need a running Postgres server.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base, get_db
from app.main import app

FIXTURES = Path(__file__).parent / "fixtures" / "edgar"


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Fresh in-memory SQLite DB per test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """FastAPI TestClient wired to our in-memory DB."""

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Fixture file loaders (used by parser tests — no DB needed)
# ---------------------------------------------------------------------------


@pytest.fixture
def fixture_13f_xml() -> bytes:
    return (FIXTURES / "13f_sample.xml").read_bytes()


@pytest.fixture
def fixture_sgml_header() -> str:
    return (FIXTURES / "13dga_sgml_header.sgml").read_text()


@pytest.fixture
def fixture_13d_primary_doc() -> str:
    return (FIXTURES / "13d_primary_doc.xml").read_text()
