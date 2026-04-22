FROM python:3.11-slim

# Keep Python logs unbuffered so structlog writes reach stdout immediately
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install deps first so code edits don't invalidate the dep layer
COPY pyproject.toml .
RUN pip install hatch && pip install -e ".[dev]"

# Now copy the app
COPY . .

# Render (and most PaaS) inject $PORT at runtime; default to 8000 locally
ENV PORT=8000
EXPOSE 8000

# Default command — overridden per-service in render.yaml / docker-compose
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
