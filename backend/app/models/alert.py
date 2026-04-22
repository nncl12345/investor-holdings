from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Alert(Base):
    """
    A user-defined watch on an investor or ticker.

    Triggers when a new filing matches the watch criteria.
    """

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    investor_id: Mapped[int | None] = mapped_column(ForeignKey("investors.id"), index=True)
    # Watch a specific ticker regardless of investor
    ticker: Mapped[str | None] = mapped_column(String(10), index=True)
    # e.g. only fire on 13D (activist) filings
    filing_type_filter: Mapped[str | None] = mapped_column(String(20))

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Delivery destination — extend as needed (webhook, email, etc.)
    webhook_url: Mapped[str | None] = mapped_column(String(512))
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    investor: Mapped["Investor | None"] = relationship(back_populates="alerts")  # noqa: F821
