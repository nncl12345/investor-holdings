from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_api_key
from app.core.db import get_db
from app.models.filing import Filing
from app.models.investor import Investor
from app.schemas.filings import FilingRead
from app.schemas.investors import InvestorCreate, InvestorRead, InvestorWithLatestFiling
from app.workers.tasks import backfill_activist_filings, ingest_quarterly_13f

router = APIRouter()


@router.get("", response_model=list[InvestorWithLatestFiling])
async def list_investors(
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """List all tracked investors with their most recent filing metadata."""
    # We want the *full row* of the most recent filing per investor (not just
    # the max date). ROW_NUMBER() OVER (PARTITION BY investor ORDER BY date DESC)
    # is portable across Postgres and SQLite; rn = 1 picks the latest.
    row_number = (
        func.row_number()
        .over(
            partition_by=Filing.investor_id,
            order_by=Filing.filing_date.desc(),
        )
        .label("rn")
    )

    ranked_sq = select(
        Filing.investor_id,
        Filing.filing_date.label("latest_date"),
        Filing.filing_type.label("latest_type"),
        row_number,
    ).subquery()
    latest_sq = select(ranked_sq).where(ranked_sq.c.rn == 1).subquery()

    result = await db.execute(
        select(
            Investor,
            latest_sq.c.latest_date,
            latest_sq.c.latest_type,
        )
        .outerjoin(latest_sq, Investor.id == latest_sq.c.investor_id)
        .order_by(latest_sq.c.latest_date.desc().nullslast())
        .offset(skip)
        .limit(limit)
    )

    rows = result.all()
    out = []
    for investor, latest_date, latest_type in rows:
        data = InvestorWithLatestFiling.model_validate(investor)
        data.latest_filing_date = latest_date.isoformat() if latest_date else None
        data.latest_filing_type = latest_type
        out.append(data)
    return out


@router.post("", response_model=InvestorRead, status_code=201, dependencies=[Depends(require_api_key)])
async def create_investor(
    body: InvestorCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add an investor to track by CIK."""
    existing = await db.execute(select(Investor).where(Investor.cik == body.cik))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Investor with this CIK already exists")

    investor = Investor(**body.model_dump())
    db.add(investor)
    await db.commit()
    await db.refresh(investor)

    # Kick off background backfill so 13D/G history appears without manual trigger
    backfill_activist_filings.delay(cik=investor.cik, investor_name=investor.name)

    return investor


@router.get("/{investor_id}", response_model=InvestorRead)
async def get_investor(investor_id: int, db: AsyncSession = Depends(get_db)):
    investor = await _get_or_404(db, investor_id)
    return investor


@router.get("/{investor_id}/filings", response_model=list[FilingRead])
async def list_investor_filings(
    investor_id: int,
    filing_type: str | None = Query(None, description="Filter by filing type, e.g. 'SC 13D'"),
    db: AsyncSession = Depends(get_db),
):
    """Return all filings for an investor, newest first."""
    await _get_or_404(db, investor_id)

    q = select(Filing).where(Filing.investor_id == investor_id)
    if filing_type:
        q = q.where(Filing.filing_type == filing_type)
    q = q.order_by(Filing.filing_date.desc())

    result = await db.execute(q)
    return result.scalars().all()


@router.post("/{investor_id}/sync", status_code=202, dependencies=[Depends(require_api_key)])
async def trigger_13f_sync(investor_id: int, db: AsyncSession = Depends(get_db)):
    """
    Manually trigger a 13F ingestion for this investor.
    Queues a Celery task and returns immediately.
    """
    investor = await _get_or_404(db, investor_id)
    ingest_quarterly_13f.delay(cik=investor.cik)
    return {"queued": True, "cik": investor.cik}


async def _get_or_404(db: AsyncSession, investor_id: int) -> Investor:
    result = await db.execute(select(Investor).where(Investor.id == investor_id))
    investor = result.scalar_one_or_none()
    if not investor:
        raise HTTPException(status_code=404, detail="Investor not found")
    return investor
