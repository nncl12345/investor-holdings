from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models as _models  # noqa: F401 — ensures all models are registered with Base
from app.core.config import settings
from app.core.db import Base, engine  # noqa: F401
from app.core.logging import RequestIdMiddleware, configure_logging

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: nothing to do here; use Alembic for schema management
    yield
    # Shutdown: dispose the connection pool
    await engine.dispose()


app = FastAPI(
    title="Investor Holdings",
    description="Track 13D/G activist filings and 13F quarterly holdings from SEC EDGAR.",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


from app.api import alerts, holdings, investors

app.include_router(investors.router, prefix="/investors", tags=["investors"])
app.include_router(holdings.router, prefix="/holdings", tags=["holdings"])
app.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
