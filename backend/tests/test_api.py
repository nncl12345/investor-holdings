"""
FastAPI route smoke tests. Uses the in-memory SQLite DB from conftest
so we don't need a running Postgres to exercise the HTTP layer.

Focus: shapes of responses, status codes, filter behaviour. Business
logic is tested elsewhere (test_diff, test_edgar_parsers).
"""

from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.filing import Filing, FilingType
from app.models.investor import Investor


async def _seed_investor_with_filings(db: AsyncSession) -> Investor:
    inv = Investor(cik="0000921669", name="Carl C Icahn", display_name="Carl Icahn")
    db.add(inv)
    await db.flush()

    db.add(
        Filing(
            investor_id=inv.id,
            filing_type=FilingType.SCHEDULE_13D_A,
            accession_number="acc-001",
            filing_date=date(2026, 4, 17),
            subject_company_name="ICAHN ENTERPRISES L.P.",
            subject_company_ticker="IEP",
            pct_owned=18.56,
            shares_owned=1870146830,
        )
    )
    db.add(
        Filing(
            investor_id=inv.id,
            filing_type=FilingType.F_13F,
            accession_number="acc-002",
            filing_date=date(2026, 2, 14),
            period_of_report=date(2025, 12, 31),
        )
    )
    await db.commit()
    return inv


class TestHealth:
    async def test_health_returns_ok(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestInvestorsEndpoint:
    async def test_empty_list(self, client: AsyncClient):
        resp = await client.get("/investors")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_populates_latest_filing(self, client: AsyncClient, db_session: AsyncSession):
        await _seed_investor_with_filings(db_session)

        resp = await client.get("/investors")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        row = data[0]
        assert row["name"] == "Carl C Icahn"
        assert row["display_name"] == "Carl Icahn"
        assert row["latest_filing_date"] == "2026-04-17"
        # This is the bug that used to return null — the fix is covered here
        assert row["latest_filing_type"] == "SCHEDULE 13D/A"

    async def test_duplicate_cik_returns_409(self, client: AsyncClient, db_session: AsyncSession):
        await _seed_investor_with_filings(db_session)
        resp = await client.post(
            "/investors",
            json={"cik": "0000921669", "name": "Duplicate"},
        )
        assert resp.status_code == 409

    async def test_get_investor_by_id(self, client: AsyncClient, db_session: AsyncSession):
        inv = await _seed_investor_with_filings(db_session)
        resp = await client.get(f"/investors/{inv.id}")
        assert resp.status_code == 200
        assert resp.json()["cik"] == "0000921669"

    async def test_get_missing_investor_returns_404(self, client: AsyncClient):
        resp = await client.get("/investors/99999")
        assert resp.status_code == 404


class TestHoldingsFeed:
    async def test_feed_returns_only_13dg_filings(self, client: AsyncClient, db_session: AsyncSession):
        # Seed includes one 13D/A and one 13F — feed should only return the 13D/A
        await _seed_investor_with_filings(db_session)

        resp = await client.get("/holdings/feed")
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 1
        assert rows[0]["filing_type"] == "SCHEDULE 13D/A"
        assert rows[0]["subject_company_ticker"] == "IEP"
        assert rows[0]["investor_name"] == "Carl C Icahn"

    async def test_feed_respects_ticker_filter(self, client: AsyncClient, db_session: AsyncSession):
        await _seed_investor_with_filings(db_session)

        match = await client.get("/holdings/feed?ticker=IEP")
        assert len(match.json()) == 1

        no_match = await client.get("/holdings/feed?ticker=XYZ")
        assert no_match.json() == []

    async def test_feed_respects_limit(self, client: AsyncClient, db_session: AsyncSession):
        await _seed_investor_with_filings(db_session)
        resp = await client.get("/holdings/feed?limit=1")
        assert resp.status_code == 200
        assert len(resp.json()) <= 1


class TestFilingDetail:
    async def test_missing_filing_returns_404(self, client: AsyncClient):
        resp = await client.get("/holdings/filings/99999")
        assert resp.status_code == 404
