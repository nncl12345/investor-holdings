from pydantic import BaseModel

from app.models.holding import ChangeType


class HoldingRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    issuer_name: str
    ticker: str | None
    cusip: str | None
    shares: int | None
    market_value_usd: int | None
    pct_of_class: float | None
    change_type: ChangeType | None
    shares_delta: int | None
    pct_delta: float | None


class HoldingDiffSummary(BaseModel):
    new: int = 0
    increased: int = 0
    decreased: int = 0
    exited: int = 0
    unchanged: int = 0
