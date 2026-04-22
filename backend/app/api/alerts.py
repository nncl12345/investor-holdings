from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_api_key
from app.core.db import get_db
from app.models.alert import Alert
from app.schemas.alerts import AlertCreate, AlertRead, AlertUpdate

router = APIRouter()


@router.get("", response_model=list[AlertRead])
async def list_alerts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Alert).order_by(Alert.created_at.desc()))
    return result.scalars().all()


@router.post("", response_model=AlertRead, status_code=201, dependencies=[Depends(require_api_key)])
async def create_alert(body: AlertCreate, db: AsyncSession = Depends(get_db)):
    """
    Create a watch on an investor (by investor_id) or a ticker.
    At least one of investor_id or ticker must be provided.
    """
    if not body.investor_id and not body.ticker:
        raise HTTPException(status_code=422, detail="Provide at least one of: investor_id, ticker")
    alert = Alert(**body.model_dump())
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return alert


@router.patch("/{alert_id}", response_model=AlertRead, dependencies=[Depends(require_api_key)])
async def update_alert(alert_id: int, body: AlertUpdate, db: AsyncSession = Depends(get_db)):
    alert = await _get_or_404(db, alert_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(alert, field, value)
    await db.commit()
    await db.refresh(alert)
    return alert


@router.delete("/{alert_id}", status_code=204, dependencies=[Depends(require_api_key)])
async def delete_alert(alert_id: int, db: AsyncSession = Depends(get_db)):
    alert = await _get_or_404(db, alert_id)
    await db.delete(alert)
    await db.commit()


async def _get_or_404(db: AsyncSession, alert_id: int) -> Alert:
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert
