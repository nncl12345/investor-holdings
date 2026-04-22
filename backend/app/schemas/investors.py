from datetime import datetime

from pydantic import BaseModel


class InvestorCreate(BaseModel):
    cik: str
    name: str
    display_name: str | None = None


class InvestorRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    cik: str
    name: str
    display_name: str | None
    created_at: datetime


class InvestorWithLatestFiling(InvestorRead):
    latest_filing_date: str | None = None
    latest_filing_type: str | None = None
