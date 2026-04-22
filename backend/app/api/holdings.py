from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_api_key
from app.core.db import get_db
from app.models.filing import Filing
from app.models.holding import ChangeType, Holding
from app.models.investor import Investor
from app.schemas.filings import FilingWithHoldings
from app.schemas.holdings import HoldingDiffSummary, HoldingRead
from app.services.diff import summarise_diff

router = APIRouter()


@router.get("/feed", response_model=list[FilingWithHoldings])
async def activist_feed(
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    filing_type: str | None = Query(None, description="e.g. 'SC 13D'"),
    ticker: str | None = Query(None, description="Filter by subject company ticker"),
):
    """
    Live feed of 13D/G activist filings, newest first.
    This is the primary surface — high-signal, low-latency events.
    """
    q = (
        select(Filing, Investor.name.label("investor_name"))
        .join(Investor, Filing.investor_id == Investor.id)
        .options(selectinload(Filing.holdings))
        .where(
            Filing.filing_type.in_(
                [
                    "SC 13D",
                    "SC 13D/A",
                    "SC 13G",
                    "SC 13G/A",
                    "SCHEDULE 13D",
                    "SCHEDULE 13D/A",
                    "SCHEDULE 13G",
                    "SCHEDULE 13G/A",
                ]
            )
        )
    )
    if filing_type:
        q = q.where(Filing.filing_type == filing_type)
    if ticker:
        q = q.where(Filing.subject_company_ticker == ticker.upper())

    q = q.order_by(Filing.filing_date.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    rows = result.all()

    return [_filing_with_summary(filing, investor_name) for filing, investor_name in rows]


@router.get("/filings/{filing_id}", response_model=FilingWithHoldings)
async def get_filing(filing_id: int, db: AsyncSession = Depends(get_db)):
    """Return a single filing with all its holdings and diff summary."""
    result = await db.execute(select(Filing).options(selectinload(Filing.holdings)).where(Filing.id == filing_id))
    filing = result.scalar_one_or_none()
    if not filing:
        raise HTTPException(status_code=404, detail="Filing not found")
    return _filing_with_summary(filing)


@router.get("/filings/{filing_id}/holdings", response_model=list[HoldingRead])
async def list_filing_holdings(
    filing_id: int,
    change_type: ChangeType | None = Query(None, description="Filter by change type"),
    min_value_usd: int | None = Query(None, description="Minimum market value in USD thousands"),
    db: AsyncSession = Depends(get_db),
):
    """
    Return holdings for a 13F filing.
    Useful for drilling into a specific quarter's portfolio.
    """
    q = select(Holding).where(Holding.filing_id == filing_id)
    if change_type:
        q = q.where(Holding.change_type == change_type)
    if min_value_usd:
        q = q.where(Holding.market_value_usd >= min_value_usd)
    q = q.order_by(Holding.market_value_usd.desc().nullslast())

    result = await db.execute(q)
    return result.scalars().all()


@router.post(
    "/filings/{filing_id}/research",
    response_model=FilingWithHoldings,
    dependencies=[Depends(require_api_key)],
)
async def research_filing(filing_id: int, db: AsyncSession = Depends(get_db)):
    """
    Trigger deep research for a 13D/G filing: web search + LLM synthesis.
    Returns the updated filing with research_summary populated.
    If research already exists, returns the cached result immediately.
    """
    result = await db.execute(select(Filing).options(selectinload(Filing.holdings)).where(Filing.id == filing_id))
    filing = result.scalar_one_or_none()
    if not filing:
        raise HTTPException(status_code=404, detail="Filing not found")

    # Return cached result if available
    if filing.research_summary:
        return _filing_with_summary(filing)

    # Resolve investor name
    inv_result = await db.execute(select(Investor).where(Investor.id == filing.investor_id))
    investor = inv_result.scalar_one_or_none()
    investor_name = (investor.display_name or investor.name) if investor else "Unknown"

    from app.services.llm import research_filing as do_research

    summary = await do_research(
        investor_name=investor_name,
        company_name=filing.subject_company_name or "Unknown company",
        filing_type=filing.filing_type,
        filing_date=str(filing.filing_date),
        transaction_purpose=filing.transaction_purpose,
        investor_id=filing.investor_id,
    )

    if summary:
        await db.execute(update(Filing).where(Filing.id == filing_id).values(research_summary=summary))
        await db.commit()
        await db.refresh(filing)

    return _filing_with_summary(filing)


@router.get("/search", response_model=list[HoldingRead])
async def search_holdings(
    ticker: str = Query(..., description="Ticker symbol to search across all filings"),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
):
    """
    Find all holdings for a given ticker across all investors and filings.
    Shows who owns it and how positions have changed over time.
    """
    result = await db.execute(
        select(Holding).where(Holding.ticker == ticker.upper()).order_by(Holding.filing_id.desc()).limit(limit)
    )
    return result.scalars().all()


def _filing_with_summary(filing: Filing, investor_name: str | None = None) -> FilingWithHoldings:
    summary_counts = summarise_diff(filing.holdings)
    diff_summary = HoldingDiffSummary(
        new=summary_counts.get(ChangeType.NEW, 0),
        increased=summary_counts.get(ChangeType.INCREASED, 0),
        decreased=summary_counts.get(ChangeType.DECREASED, 0),
        exited=summary_counts.get(ChangeType.EXITED, 0),
        unchanged=summary_counts.get(ChangeType.UNCHANGED, 0),
    )
    data = FilingWithHoldings.model_validate(filing)
    data.diff_summary = diff_summary
    data.investor_name = investor_name
    return data
