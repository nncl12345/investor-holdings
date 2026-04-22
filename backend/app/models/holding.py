from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class ChangeType(StrEnum):
    NEW = "new"  # Position opened this quarter
    INCREASED = "increased"
    DECREASED = "decreased"
    EXITED = "exited"  # Position closed this quarter
    UNCHANGED = "unchanged"


class Holding(Base):
    """
    A single equity position within a filing.

    For 13F: one row per issuer per filing.
    For 13D/G: one row representing the disclosed stake.
    """

    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(primary_key=True)
    filing_id: Mapped[int] = mapped_column(ForeignKey("filings.id"), index=True)

    issuer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    ticker: Mapped[str | None] = mapped_column(String(10), index=True)
    cusip: Mapped[str | None] = mapped_column(String(9), index=True)

    # Shares held (13F) or shares/units disclosed (13D/G)
    shares: Mapped[int | None] = mapped_column(BigInteger)
    # Market value in USD thousands (as reported in 13F)
    market_value_usd: Mapped[int | None] = mapped_column(BigInteger)
    # Percentage of class owned (13D/G)
    pct_of_class: Mapped[float | None] = mapped_column(Numeric(5, 2))

    # Computed diff vs previous period — populated by diff service
    change_type: Mapped[ChangeType | None] = mapped_column(String(20), index=True)
    shares_delta: Mapped[int | None] = mapped_column(BigInteger)
    pct_delta: Mapped[float | None] = mapped_column(Numeric(7, 2))

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    filing: Mapped["Filing"] = relationship(back_populates="holdings")  # noqa: F821
