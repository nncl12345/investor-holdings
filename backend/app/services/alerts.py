"""
Alert dispatch service.

When a new filing is ingested, this service checks whether any Alert
rows match it and fires the configured delivery (webhook for now).
"""

import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert
from app.models.filing import Filing

logger = logging.getLogger(__name__)


async def dispatch_for_filing(db: AsyncSession, filing: Filing) -> None:
    """
    Find all enabled alerts that match `filing` and dispatch them.
    Matching logic:
      - investor_id matches (watch a specific investor), OR
      - ticker matches the subject company ticker (watch a ticker across all filers)
      - filing_type_filter matches (optional — e.g. only 13D, not 13G)
    """
    result = await db.execute(select(Alert).where(Alert.enabled == True))  # noqa: E712
    alerts = result.scalars().all()

    for alert in alerts:
        if not _matches(alert, filing):
            continue
        await _dispatch(alert, filing)
        alert.last_triggered_at = datetime.now(UTC)

    await db.commit()


def _matches(alert: Alert, filing: Filing) -> bool:
    # Must match at least one of: investor or ticker
    investor_match = alert.investor_id is not None and alert.investor_id == filing.investor_id
    ticker_match = (
        alert.ticker is not None
        and filing.subject_company_ticker is not None
        and alert.ticker.upper() == filing.subject_company_ticker.upper()
    )
    if not (investor_match or ticker_match):
        return False

    # Optional filing type filter
    if alert.filing_type_filter and alert.filing_type_filter != filing.filing_type:
        return False

    return True


async def _dispatch(alert: Alert, filing: Filing) -> None:
    if alert.webhook_url:
        await _send_webhook(alert.webhook_url, filing)
    else:
        # Fallback: log — extend here for email, Slack, push, etc.
        logger.info(
            "Alert %d triggered: %s filed %s on %s",
            alert.id,
            filing.investor_id,
            filing.filing_type,
            filing.filing_date,
        )


async def _send_webhook(url: str, filing: Filing) -> None:
    payload = {
        "event": "new_filing",
        "filing_type": filing.filing_type,
        "filing_date": filing.filing_date.isoformat() if filing.filing_date else None,
        "accession_number": filing.accession_number,
        "subject_company": filing.subject_company_name,
        "subject_ticker": filing.subject_company_ticker,
        "raw_url": filing.raw_url,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            logger.info("Webhook delivered to %s for filing %s", url, filing.accession_number)
    except httpx.HTTPError:
        logger.exception("Webhook delivery failed for alert targeting %s", url)
