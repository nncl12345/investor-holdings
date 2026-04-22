"""
One-off script: backfill transaction_summary for filings that have transaction_purpose
but no summary yet.

Usage:
  cd backend
  ANTHROPIC_API_KEY=sk-... .venv/bin/python scripts/backfill_summaries.py
"""

import asyncio
import os
import sys

# Ensure app is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select, update

from app.core.db import AsyncSessionLocal
from app.models.filing import Filing
from app.services.llm import summarize_transaction_purpose


async def main() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Filing.id, Filing.transaction_purpose)
            .where(Filing.transaction_purpose.isnot(None))
            .where(Filing.transaction_summary.is_(None))
        )
        rows = result.all()

    print(f"Found {len(rows)} filings to summarise")

    for i, (filing_id, purpose) in enumerate(rows, 1):
        summary = await summarize_transaction_purpose(purpose)
        if summary:
            async with AsyncSessionLocal() as db:
                await db.execute(update(Filing).where(Filing.id == filing_id).values(transaction_summary=summary))
                await db.commit()
            print(f"[{i}/{len(rows)}] #{filing_id} → {summary[:80]}...")
        else:
            print(f"[{i}/{len(rows)}] #{filing_id} → (no summary)")
        await asyncio.sleep(12)  # free tier: 6000 TPM — ~12s between requests is safe

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
