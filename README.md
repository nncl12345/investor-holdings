# Investor Holdings — SEC activist-filing intelligence platform

Real-time tracker for SEC **13D/G** (activist) and **13F** (institutional) filings across a curated list of funds (Elliott, Jana, Pershing Square, Starboard, Third Point, …). Ingests live from EDGAR, runs a quarter-over-quarter diff engine on 13F holdings, and enriches each 13D/G with an LLM-generated thesis + deep research summary.

## Why this project

Bloomberg terminals show you the raw filings. They don't tell you what a filing *means* in context — or when multiple activists are piling into the same name. Two domain points drive the design:

1. **13Fs are stale by design.** Filed 45 days after quarter-end, they tell you what a fund held 6+ weeks ago. The primary real-time signal is 13D/G — filed within 10 days of crossing 5% ownership. So the homepage is a 13D/G feed, not a portfolio view.
2. **Crowded activist trades have asymmetric payoffs.** When Jana, Starboard, and Elliott all file on the same ticker within 60 days, that's signal — a single feed won't surface it. A consensus view across tracked funds does.

## Tech stack

| Layer | Tools |
|---|---|
| API | Python 3.11, FastAPI (async), SQLAlchemy 2.0, Alembic |
| Workers | Celery (beat + worker), Redis |
| Storage | PostgreSQL 16 |
| Ingestion | httpx against `data.sec.gov/submissions`, SGML + XML parsers for 13D/G + 13F-HR |
| LLM | Groq (fast transaction-purpose summaries), Claude Sonnet + Tavily (deep research w/ citations) |
| Frontend | Next.js 14 (app router), React 19, TypeScript, Tailwind, shadcn/ui |
| Observability | structlog (JSON) + request-ID middleware |
| CI | GitHub Actions (ruff, mypy, pytest, `tsc --noEmit`, `next lint`) |

## Architecture

```
  SEC EDGAR
    │
    ├─ data.sec.gov/submissions (polled every 30m)
    │        │
    │        ▼
    │  Celery worker ── parses SGML / XML ──▶ Postgres
    │        │                                  │
    │        ├─ 13D/G ─ subject company lookup  │
    │        └─ 13F-HR ─ run diff engine ───────┘
    │                                           │
    │                                           ▼
    │                                    FastAPI (async SQLAlchemy)
    │                                           │
    │                                           ▼
    │                                    Next.js frontend
    │
    └─ LLM enrichment (side-loop)
         • Groq — fast 1–2 sentence thesis on transaction_purpose
         • Claude + Tavily — deep research w/ citations (on demand)
```

## Features

- **Live 13D/G feed** with parsed subject-company metadata (CIK, ticker, CUSIP), disclosed % owned, and an LLM-generated 1-sentence thesis of Item 4 ("purpose of transaction")
- **13F portfolio tracker** with a quarter-over-quarter diff engine tagging every position as `new / increased / decreased / exited / unchanged`
- **Multi-step research agent** — classify campaign → dynamic web search (Tavily) → cross-reference investor's own filing history → synthesise a cited summary
- **Watch alerts** — webhook-dispatched when a matching filing lands (filter by `investor_id`, `ticker`, `filing_type`)
- **Public read API**, API-key-gated writes (see `app/api/deps.py`)

## Running locally

### Prerequisites

- Docker + Docker Compose
- Python 3.11 (only if working on the backend outside Docker)
- Node 20+ (only for frontend dev outside Docker)

### Start

```bash
# 1. Backend + db + redis + worker + beat
cp backend/.env.example backend/.env   # edit: EDGAR_USER_AGENT, GROQ_API_KEY, TAVILY_API_KEY
docker compose up -d

# 2. Apply migrations
docker compose exec api alembic upgrade head

# 3. Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

Backend at `http://localhost:8000` (`/docs` for OpenAPI). Frontend at `http://localhost:3000`.

### Seed some data

```bash
# Add an investor by CIK — triggers background backfill of their full 13D/G history
curl -X POST http://localhost:8000/investors \
  -H "Content-Type: application/json" \
  -d '{"cik": "0001038154", "name": "Elliott Investment Management"}'

# Kick off 13F ingestion
curl -X POST http://localhost:8000/investors/1/sync
```

## Tests

```bash
cd backend && pytest         # ~32 tests: EDGAR parsers, diff engine, API smoke tests
cd frontend && npx tsc --noEmit && npx next lint
```

CI runs the same on every push — see `.github/workflows/ci.yml`.

## Security notes

- **`.env` is git-ignored.** Never commit real API keys. See `backend/.env.example` for the full list.
- **Write endpoints are gated.** `POST /investors`, `POST /investors/{id}/sync`, `POST /holdings/filings/{id}/research`, and all `/alerts` mutations require `X-API-Key: <secret>` when `API_KEY` is set. Reads stay public — the demo is read-only by design.
- **CORS is env-driven.** Set `CORS_ALLOWED_ORIGINS` to a comma-separated list of your frontend origins. Defaults to `localhost:3000` for local dev.
- **SEC rate limits.** EDGAR allows ~10 req/s with a descriptive User-Agent. The Celery beat schedule respects that; ad-hoc scripts should too.

## Roadmap

- `/consensus` view — crowded names across tracked investors, "who moved first"
- Claude Sonnet agent rewrite for `/research` (currently Groq + Tavily; plan in `app/services/llm.py`)
- 30/60/90-day post-filing return backtest vs SPY
- Stock price overlay on filing timelines

## Honest limitations

- Some filers (e.g. Third Point) self-file on multiple internal fund vehicles; the tracker treats each as a separate investor
- EDGAR SGML headers frequently omit `TRADING-SYMBOL` — we fall back to looking up the subject CIK in `data.sec.gov/submissions`, but coverage isn't 100%
- 13F XML schemas changed in 2013 — older filings parse with reduced field coverage
