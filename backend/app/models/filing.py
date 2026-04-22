from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class FilingType(StrEnum):
    SC_13D = "SC 13D"  # Activist — crosses 5%, intent to influence
    SC_13D_A = "SC 13D/A"  # Amendment to 13D
    SC_13G = "SC 13G"  # Passive — crosses 5%, no activist intent
    SC_13G_A = "SC 13G/A"  # Amendment to 13G
    SCHEDULE_13D = "SCHEDULE 13D"  # Same as SC 13D, newer EDGAR naming
    SCHEDULE_13D_A = "SCHEDULE 13D/A"  # Same as SC 13D/A
    SCHEDULE_13G = "SCHEDULE 13G"  # Same as SC 13G
    SCHEDULE_13G_A = "SCHEDULE 13G/A"  # Same as SC 13G/A
    F_13F = "13F-HR"  # Quarterly institutional holdings report
    F_13F_A = "13F-HR/A"  # Amendment to 13F


class Filing(Base):
    """A single SEC filing (13D, 13G, or 13F) by an investor."""

    __tablename__ = "filings"

    id: Mapped[int] = mapped_column(primary_key=True)
    investor_id: Mapped[int] = mapped_column(ForeignKey("investors.id"), index=True)
    filing_type: Mapped[FilingType] = mapped_column(String(20), nullable=False, index=True)

    # EDGAR identifiers
    accession_number: Mapped[str] = mapped_column(String(25), unique=True, nullable=False)
    filing_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # For 13F: the quarter this report covers (e.g. 2024-12-31)
    period_of_report: Mapped[date | None] = mapped_column(Date)

    # For 13D/G: the target company
    subject_company_name: Mapped[str | None] = mapped_column(String(255))
    subject_company_ticker: Mapped[str | None] = mapped_column(String(10), index=True)
    subject_company_cusip: Mapped[str | None] = mapped_column(String(9))

    raw_url: Mapped[str | None] = mapped_column(String(512))

    # 13D/G position details (parsed from primary_doc.xml when available)
    shares_owned: Mapped[int | None] = mapped_column()
    pct_owned: Mapped[float | None] = mapped_column()
    transaction_purpose: Mapped[str | None] = mapped_column()
    transaction_summary: Mapped[str | None] = mapped_column()  # LLM-generated 1-2 sentence thesis
    research_summary: Mapped[str | None] = mapped_column()  # Deep research: web search + LLM synthesis

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    investor: Mapped["Investor"] = relationship(back_populates="filings")  # noqa: F821
    holdings: Mapped[list["Holding"]] = relationship(back_populates="filing")  # noqa: F821
