from datetime import date, datetime

from pydantic import BaseModel

from app.models.filing import FilingType
from app.schemas.holdings import HoldingDiffSummary, HoldingRead


class FilingRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    investor_id: int
    filing_type: FilingType
    accession_number: str
    filing_date: date
    period_of_report: date | None
    subject_company_name: str | None
    subject_company_ticker: str | None
    subject_company_cusip: str | None
    raw_url: str | None
    shares_owned: int | None
    pct_owned: float | None
    transaction_purpose: str | None
    transaction_summary: str | None
    research_summary: str | None
    created_at: datetime


class FilingWithHoldings(FilingRead):
    holdings: list[HoldingRead] = []
    diff_summary: HoldingDiffSummary | None = None
    investor_name: str | None = None
