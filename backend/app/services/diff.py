"""
Quarter-over-quarter diff engine for 13F holdings.

Given two consecutive 13F filings for the same investor, computes
what was opened, closed, increased, or decreased between periods.

13D/G filings don't need diffing — each one is already an event.
"""

import logging
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.filing import Filing, FilingType
from app.models.holding import ChangeType, Holding

logger = logging.getLogger(__name__)


async def compute_13f_diff(db: AsyncSession, current_filing: Filing) -> None:
    """
    Compare `current_filing` against the investor's previous 13F and
    annotate each Holding row with a change_type, shares_delta, and pct_delta.

    Runs after a new 13F is ingested. Safe to re-run (idempotent).
    """
    if current_filing.filing_type != FilingType.F_13F:
        return

    previous = await _get_previous_13f(db, current_filing)
    if previous is None:
        # First filing for this investor — mark everything as NEW
        await _mark_all(db, current_filing, ChangeType.NEW)
        return

    prev_holdings = await _holdings_by_cusip(db, previous.id)
    curr_holdings = await _holdings_by_cusip(db, current_filing.id)

    all_cusips = set(prev_holdings) | set(curr_holdings)

    for cusip in all_cusips:
        prev = prev_holdings.get(cusip)
        curr = curr_holdings.get(cusip)

        if curr is None:
            # Position existed before but is gone now — mark the previous holding
            if prev:
                prev.change_type = ChangeType.EXITED
            continue

        if prev is None:
            curr.change_type = ChangeType.NEW
            curr.shares_delta = curr.shares
            curr.pct_delta = None
            continue

        delta = (curr.shares or 0) - (prev.shares or 0)
        curr.shares_delta = delta

        if prev.shares and prev.shares != 0:
            curr.pct_delta = round((delta / prev.shares) * 100, 2)

        if delta > 0:
            curr.change_type = ChangeType.INCREASED
        elif delta < 0:
            curr.change_type = ChangeType.DECREASED
        else:
            curr.change_type = ChangeType.UNCHANGED

    await db.commit()
    logger.info(
        "Diff complete for filing %s vs %s",
        current_filing.accession_number,
        previous.accession_number,
    )


def summarise_diff(holdings: list[Holding]) -> dict:
    """
    Return a summary dict of change counts for a filing's holdings.
    Useful for the API response and alert triggers.
    """
    counts: dict[str, int] = defaultdict(int)
    for h in holdings:
        counts[h.change_type or ChangeType.UNCHANGED] += 1
    return dict(counts)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_previous_13f(db: AsyncSession, filing: Filing) -> Filing | None:
    """Return the 13F filed immediately before `filing` for the same investor."""
    result = await db.execute(
        select(Filing)
        .where(
            Filing.investor_id == filing.investor_id,
            Filing.filing_type == FilingType.F_13F,
            Filing.period_of_report < filing.period_of_report,
        )
        .order_by(Filing.period_of_report.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _holdings_by_cusip(db: AsyncSession, filing_id: int) -> dict[str, Holding]:
    """Return a {cusip: Holding} map for a given filing. Skips rows without CUSIP."""
    result = await db.execute(
        select(Holding).where(
            Holding.filing_id == filing_id,
            Holding.cusip.isnot(None),
        )
    )
    holdings = result.scalars().all()
    # If multiple rows share a CUSIP (shouldn't happen in clean 13F data), last one wins
    return {h.cusip: h for h in holdings if h.cusip is not None}


async def _mark_all(db: AsyncSession, filing: Filing, change_type: ChangeType) -> None:
    result = await db.execute(select(Holding).where(Holding.filing_id == filing.id))
    for holding in result.scalars().all():
        holding.change_type = change_type
        if change_type == ChangeType.NEW:
            holding.shares_delta = holding.shares  # First filing — full position is "new"
    await db.commit()
