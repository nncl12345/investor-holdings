FROM python:3.11-slim

WORKDIR /app

RUN pip install hatch

COPY pyproject.toml .
RUN pip install -e ".[dev]"

COPY . .
