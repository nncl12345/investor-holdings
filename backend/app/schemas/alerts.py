from datetime import datetime

from pydantic import BaseModel


class AlertCreate(BaseModel):
    investor_id: int | None = None
    ticker: str | None = None
    filing_type_filter: str | None = None
    webhook_url: str | None = None


class AlertUpdate(BaseModel):
    enabled: bool | None = None
    webhook_url: str | None = None
    filing_type_filter: str | None = None


class AlertRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    investor_id: int | None
    ticker: str | None
    filing_type_filter: str | None
    enabled: bool
    webhook_url: str | None
    last_triggered_at: datetime | None
    created_at: datetime
