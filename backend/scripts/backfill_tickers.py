"""
One-off script: backfill subject_company_ticker for 13D/G filings that are
missing it. Re-fetches the .hdr.sgml header to get the subject CIK, then
looks up the ticker via data.sec.gov/submissions/CIK{cik}.json.

Usage:
  cd backend
  .venv/bin/python scripts/backfill_tickers.py
"""

import asyncio
import os
import sys

# Ensure app is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select, update

from app.core.db import AsyncSessionLocal
from app.models.filing import Filing
from app.models.investor import Investor
from app.services.edgar import fetch_filing_index


async def main() -> None:
    updated = 0
    scanned = 0

    async with AsyncSessionLocal() as db:
        # Find 13D/G filings missing ticker but with a subject company name
        # (excludes 13F-HR rows which don't have a subject company).
        result = await db.execute(
            select(Filing.id, Filing.accession_number, Investor.cik, Filing.subject_company_name)
            .join(Investor, Filing.investor_id == Investor.id)
            .where(Filing.subject_company_ticker.is_(None))
            .where(Filing.subject_company_name.isnot(None))
            .where(Filing.filing_type.notin_(["13F-HR", "13F-HR/A"]))
        )
        rows = result.all()

    print(f"Found {len(rows)} filings missing a ticker. Starting lookup…")

    for filing_id, acc, investor_cik, company in rows:
        scanned += 1
        try:
            meta = await fetch_filing_index(acc, investor_cik)
        except Exception as e:
            print(f"  [{filing_id}] {company!r}: lookup failed: {e}")
            continue

        ticker = meta.get("subject_company_ticker")
        if not ticker:
            continue

        async with AsyncSessionLocal() as db:
            await db.execute(update(Filing).where(Filing.id == filing_id).values(subject_company_ticker=ticker))
            await db.commit()
        updated += 1
        print(f"  [{filing_id}] {company!r} -> {ticker}")

        if scanned % 25 == 0:
            print(f"  progress: {scanned}/{len(rows)} scanned, {updated} tickers filled")

    print(f"\nDone. Scanned {scanned}, updated {updated}.")


if __name__ == "__main__":
    asyncio.run(main())
