from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Investor(Base):
    """An institutional investor or activist filer tracked by CIK."""

    __tablename__ = "investors"

    id: Mapped[int] = mapped_column(primary_key=True)
    cik: Mapped[str] = mapped_column(String(10), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # e.g. "Berkshire Hathaway", "Pershing Square Capital Management"
    display_name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    filings: Mapped[list["Filing"]] = relationship(back_populates="investor")  # noqa: F821
    alerts: Mapped[list["Alert"]] = relationship(back_populates="investor")  # noqa: F821
