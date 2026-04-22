"""
Tests for the quarter-over-quarter 13F diff engine.

Strategy: set up two sequential 13F filings for a single investor with
synthetic holdings that exercise every branch of compute_13f_diff
(NEW / INCREASED / DECREASED / EXITED / UNCHANGED), then assert the
annotations are correct.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.filing import Filing, FilingType
from app.models.holding import ChangeType, Holding
from app.models.investor import Investor
from app.services.diff import compute_13f_diff, summarise_diff


async def _make_investor(db: AsyncSession) -> Investor:
    inv = Investor(cik="0001234567", name="Test Fund")
    db.add(inv)
    await db.flush()
    return inv


async def _make_13f(db: AsyncSession, investor: Investor, period: date, acc: str, holdings: list[dict]) -> Filing:
    filing = Filing(
        investor_id=investor.id,
        filing_type=FilingType.F_13F,
        accession_number=acc,
        filing_date=period,
        period_of_report=period,
    )
    db.add(filing)
    await db.flush()
    for h in holdings:
        db.add(Holding(filing_id=filing.id, **h))
    await db.commit()
    await db.refresh(filing)
    return filing


async def _refresh_holdings(db: AsyncSession, filing_id: int) -> list[Holding]:
    result = await db.execute(select(Holding).where(Holding.filing_id == filing_id))
    return list(result.scalars().all())


class TestCompute13FDiff:
    async def test_first_filing_all_new(self, db_session: AsyncSession):
        inv = await _make_investor(db_session)
        filing = await _make_13f(
            db_session,
            inv,
            date(2024, 3, 31),
            "acc-001",
            [
                {"issuer_name": "Apple", "cusip": "037833100", "shares": 100, "market_value_usd": 18000},
                {"issuer_name": "Microsoft", "cusip": "594918104", "shares": 50, "market_value_usd": 20000},
            ],
        )
        await compute_13f_diff(db_session, filing)

        holdings = await _refresh_holdings(db_session, filing.id)
        assert len(holdings) == 2
        assert all(h.change_type == ChangeType.NEW for h in holdings)
        assert all(h.shares_delta == h.shares for h in holdings)

    async def test_second_filing_mixed_changes(self, db_session: AsyncSession):
        inv = await _make_investor(db_session)

        # Q1: Apple 100, MSFT 50, Nvidia 10
        q1 = await _make_13f(
            db_session,
            inv,
            date(2024, 3, 31),
            "acc-q1",
            [
                {"issuer_name": "Apple", "cusip": "037833100", "shares": 100, "market_value_usd": 18000},
                {"issuer_name": "Microsoft", "cusip": "594918104", "shares": 50, "market_value_usd": 20000},
                {"issuer_name": "Nvidia", "cusip": "67066G104", "shares": 10, "market_value_usd": 5000},
            ],
        )
        await compute_13f_diff(db_session, q1)

        # Q2: Apple 150 (INCREASED), MSFT 50 (UNCHANGED), Nvidia gone (EXITED),
        #     Tesla 20 (NEW), Google 30 (NEW)
        q2 = await _make_13f(
            db_session,
            inv,
            date(2024, 6, 30),
            "acc-q2",
            [
                {"issuer_name": "Apple", "cusip": "037833100", "shares": 150, "market_value_usd": 27000},
                {"issuer_name": "Microsoft", "cusip": "594918104", "shares": 50, "market_value_usd": 22000},
                {"issuer_name": "Tesla", "cusip": "88160R101", "shares": 20, "market_value_usd": 4000},
                {"issuer_name": "Google", "cusip": "02079K305", "shares": 30, "market_value_usd": 4500},
            ],
        )
        await compute_13f_diff(db_session, q2)

        # Verify Q2 annotations
        q2_holdings = {h.cusip: h for h in await _refresh_holdings(db_session, q2.id)}
        assert q2_holdings["037833100"].change_type == ChangeType.INCREASED
        assert q2_holdings["037833100"].shares_delta == 50
        assert q2_holdings["037833100"].pct_delta == 50.0  # 50/100 * 100
        assert q2_holdings["594918104"].change_type == ChangeType.UNCHANGED
        assert q2_holdings["594918104"].shares_delta == 0
        assert q2_holdings["88160R101"].change_type == ChangeType.NEW
        assert q2_holdings["02079K305"].change_type == ChangeType.NEW

        # EXITED marking is applied to the *previous* filing's row
        q1_holdings = {h.cusip: h for h in await _refresh_holdings(db_session, q1.id)}
        assert q1_holdings["67066G104"].change_type == ChangeType.EXITED

    async def test_decreased_position(self, db_session: AsyncSession):
        inv = await _make_investor(db_session)
        q1 = await _make_13f(
            db_session,
            inv,
            date(2024, 3, 31),
            "acc-a",
            [{"issuer_name": "Apple", "cusip": "037833100", "shares": 100, "market_value_usd": 18000}],
        )
        await compute_13f_diff(db_session, q1)

        q2 = await _make_13f(
            db_session,
            inv,
            date(2024, 6, 30),
            "acc-b",
            [{"issuer_name": "Apple", "cusip": "037833100", "shares": 60, "market_value_usd": 11000}],
        )
        await compute_13f_diff(db_session, q2)

        holdings = await _refresh_holdings(db_session, q2.id)
        assert holdings[0].change_type == ChangeType.DECREASED
        assert holdings[0].shares_delta == -40
        assert holdings[0].pct_delta == -40.0

    async def test_ignores_non_13f_filing(self, db_session: AsyncSession):
        inv = await _make_investor(db_session)
        filing = Filing(
            investor_id=inv.id,
            filing_type=FilingType.SCHEDULE_13D,
            accession_number="13d-acc",
            filing_date=date(2024, 5, 1),
            subject_company_name="Target Co",
        )
        db_session.add(filing)
        await db_session.commit()

        # Should be a no-op for non-13F filings
        await compute_13f_diff(db_session, filing)


class TestSummariseDiff:
    def test_counts_each_change_type(self):
        holdings = [
            Holding(change_type=ChangeType.NEW, issuer_name="A"),
            Holding(change_type=ChangeType.NEW, issuer_name="B"),
            Holding(change_type=ChangeType.INCREASED, issuer_name="C"),
            Holding(change_type=ChangeType.EXITED, issuer_name="D"),
        ]
        counts = summarise_diff(holdings)
        assert counts[ChangeType.NEW] == 2
        assert counts[ChangeType.INCREASED] == 1
        assert counts[ChangeType.EXITED] == 1
        assert counts.get(ChangeType.DECREASED, 0) == 0

    def test_none_change_type_counted_as_unchanged(self):
        holdings = [Holding(change_type=None, issuer_name="A")]
        counts = summarise_diff(holdings)
        assert counts[ChangeType.UNCHANGED] == 1
