"""
Structured JSON logging with structlog + request-ID context.

Every log line includes a request_id (when emitted from inside a FastAPI request),
so you can grep any single user's journey through the whole app in prod logs.
Uses JSON output which Fly.io / Datadog / anything else can parse directly.
"""

from __future__ import annotations

import logging
import sys
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


def configure_logging(*, level: str = "INFO", json_output: bool = True) -> None:
    """
    Wire structlog into the stdlib logging chain.

    - stdlib loggers (uvicorn, sqlalchemy, httpx…) all route through the same
      structlog processor chain and come out as JSON.
    - `request_id` is pulled from contextvars, so any log call anywhere in a
      request picks it up automatically.
    """
    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer() if json_output else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging through structlog too, so third-party libs line up
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                renderer,
            ],
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    # Quiet the noisier libraries a bit
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel("WARNING")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Assign each request a UUID4, bind it into structlog's contextvars so every
    log emitted during the request carries it, and echo it back as the
    `X-Request-ID` response header for client-side correlation.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            path=request.url.path,
            method=request.method,
        )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
