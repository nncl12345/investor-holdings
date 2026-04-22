"""
Celery task definitions.

Two scheduled tasks:
  - poll_activist_filings  — runs every 30 minutes, catches 13D/G as they drop
  - ingest_quarterly_13f   — runs weekly around filing deadlines (mid-Feb/May/Aug/Nov)

Run worker:  celery -A app.workers.tasks worker --loglevel=info
Run beat:    celery -A app.workers.tasks beat   --loglevel=info
"""

import asyncio
import logging
from datetime import date, timedelta

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "investor_holdings",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        # 13D/G: poll every 30 minutes during market hours (Mon–Fri, 8am–8pm UTC)
        "poll-activist-filings": {
            "task": "app.workers.tasks.poll_activist_filings",
            "schedule": crontab(minute="*/30", hour="8-20", day_of_week="1-5"),
        },
        # 13F: weekly sweep — useful during the 45-day filing windows
        "ingest-quarterly-13f": {
            "task": "app.workers.tasks.ingest_quarterly_13f",
            "schedule": crontab(hour=2, minute=0, day_of_week=1),  # Every Monday 2am UTC
        },
    },
)


def _run(coro):
    """Run an async coroutine from a sync Celery task."""
    return asyncio.get_event_loop().run_until_complete(coro)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def poll_activist_filings(self):
    """
    Fetch recent 13D/G filings from EDGAR and persist any new ones.
    Fires alert dispatches for matching user watches.
    """
    try:
        _run(_poll_activist_filings_async())
    except Exception as exc:
        logger.exception("poll_activist_filings failed")
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def backfill_activist_filings(self, cik: str, investor_name: str = ""):
    """
    Backfill all historical 13D/G filings for a newly-added investor.
    Called automatically when a new investor is created via the API.
    """
    try:
        _run(_backfill_activist_filings_async(cik, investor_name))
    except Exception as exc:
        logger.exception("backfill_activist_filings failed for cik=%s", cik)
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def ingest_quarterly_13f(self, cik: str | None = None):
    """
    Ingest 13F holdings for all tracked investors (or a single CIK if provided).
    Runs the diff engine after each new filing is stored.
    """
    try:
        _run(_ingest_quarterly_13f_async(cik))
    except Exception as exc:
        logger.exception("ingest_quarterly_13f failed for cik=%s", cik)
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Async implementations
# ---------------------------------------------------------------------------


async def _poll_activist_filings_async():
    """
    Scan all tracked investors' submission histories for new 13D/G filings.
    Uses data.sec.gov/submissions (reliable) rather than the EDGAR full-text
    search index (which has known date-range issues).
    """
    from sqlalchemy import select

    from app.core.db import AsyncSessionLocal
    from app.models.investor import Investor
    from app.services import alerts as alert_service
    from app.services.edgar import (
        fetch_filing_index,
        fetch_recent_activist_filings_for_investor,
        filing_exists,
        persist_activist_filing,
        upsert_investor,
    )

    since = date.today() - timedelta(days=2)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Investor))
        investors = result.scalars().all()

        new_count = 0
        for investor in investors:
            filings = await fetch_recent_activist_filings_for_investor(cik=investor.cik, since=since)
            for parsed in filings:
                acc = parsed["accession_number"]
                if not acc or await filing_exists(db, acc):
                    continue

                inv = await upsert_investor(db, cik=investor.cik, name=investor.name)
                index_meta = await fetch_filing_index(acc, investor.cik)
                filing = await persist_activist_filing(db, inv, parsed, index_meta)
                new_count += 1
                await alert_service.dispatch_for_filing(db, filing)

        logger.info("poll_activist_filings: ingested %d new 13D/G filings", new_count)


async def _backfill_activist_filings_async(cik: str, investor_name: str):
    """Fetch all 13D/G history for a single investor and persist new filings."""
    from datetime import date

    from app.core.db import AsyncSessionLocal
    from app.services.edgar import (
        fetch_filing_index,
        fetch_recent_activist_filings_for_investor,
        filing_exists,
        persist_activist_filing,
        upsert_investor,
    )

    since = date(2000, 1, 1)  # far enough back to capture full history

    async with AsyncSessionLocal() as db:
        inv = await upsert_investor(db, cik=cik, name=investor_name)
        filings = await fetch_recent_activist_filings_for_investor(cik=cik, since=since)

        new_count = 0
        for parsed in filings:
            acc = parsed["accession_number"]
            if not acc or await filing_exists(db, acc):
                continue
            index_meta = await fetch_filing_index(acc, cik)
            await persist_activist_filing(db, inv, parsed, index_meta)
            new_count += 1

        logger.info(
            "backfill_activist_filings: ingested %d new 13D/G filings for CIK %s",
            new_count,
            cik,
        )


async def _ingest_quarterly_13f_async(cik: str | None):

    from sqlalchemy import select

    from app.core.db import AsyncSessionLocal
    from app.models.filing import Filing, FilingType
    from app.models.investor import Investor
    from app.services.diff import compute_13f_diff
    from app.services.edgar import (
        fetch_13f_xml,
        fetch_investor_submissions,
        filing_exists,
        persist_13f_holdings,
        upsert_investor,
    )

    async with AsyncSessionLocal() as db:
        # Determine which investors to process
        if cik:
            investors = [await upsert_investor(db, cik=cik, name="")]
        else:
            result = await db.execute(select(Investor))
            investors = list(result.scalars().all())

        for investor in investors:
            try:
                submissions = await fetch_investor_submissions(investor.cik)
                # Process oldest-first so diffs (which look backward) work correctly
                recent_13f = list(reversed(_extract_recent_13f(submissions)))

                for filing_meta in recent_13f:
                    acc = filing_meta["accessionNumber"].replace("-", "")
                    if await filing_exists(db, acc):
                        continue

                    filing = Filing(
                        investor_id=investor.id,
                        filing_type=FilingType.F_13F,
                        accession_number=acc,
                        filing_date=_parse_date(filing_meta.get("filingDate")),
                        period_of_report=_parse_date(filing_meta.get("reportDate")),
                    )
                    db.add(filing)
                    await db.flush()

                    positions = await fetch_13f_xml(acc, investor.cik)
                    await persist_13f_holdings(db, filing, positions)
                    await compute_13f_diff(db, filing)

                    logger.info(
                        "Ingested 13F %s for investor %s (%d positions)",
                        acc,
                        investor.cik,
                        len(positions),
                    )
            except Exception:
                logger.exception("Failed to ingest 13F for investor CIK %s", investor.cik)
                continue


def _extract_recent_13f(submissions: dict, limit: int = 4) -> list[dict]:
    """
    Pull the most recent 13F-HR filings from a submissions JSON response.
    Returns up to `limit` filings in reverse-chronological order.
    """
    filings = submissions.get("filings", {}).get("recent", {})
    form_types = filings.get("form", [])
    acc_numbers = filings.get("accessionNumber", [])
    filing_dates = filings.get("filingDate", [])
    report_dates = filings.get("reportDate", [])

    results = []
    for i, form in enumerate(form_types):
        if form == "13F-HR":
            results.append(
                {
                    "accessionNumber": acc_numbers[i],
                    "filingDate": filing_dates[i],
                    "reportDate": report_dates[i] if i < len(report_dates) else None,
                }
            )
        if len(results) >= limit:
            break

    return results


def _extract_cik(hit: dict) -> str | None:
    """Extract the CIK from an EDGAR search hit."""
    # The _id field is the accession number; CIK is the first 10 digits
    acc_id = hit.get("_id", "")
    clean = acc_id.replace("-", "")
    if len(clean) >= 10:
        return clean[:10].lstrip("0")
    return None


def _parse_date(value: str | None):
    if not value:
        return None
    from datetime import datetime

    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
