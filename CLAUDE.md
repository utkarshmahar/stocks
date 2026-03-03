# Options Trading AI Platform — CLAUDE.md

This file is the master reference for Claude Code to understand, plan, and implement this system.
Read this fully before making any changes.

---

## Project Vision

A microservices-based options trading intelligence platform running on a Raspberry Pi (and/or cloud).
It streams live options chain data from Schwab, stores it in InfluxDB, runs AI agents for trade ideas,
performs deep fundamental analysis, and displays everything in a React dashboard.

---

## System Architecture

```
Schwab API (Options Chain + Stock Prices)
        │
        ▼
Data Ingestion Service (Python + Async + Celery)
        │
        ▼
InfluxDB (Time-Series: ticks, IV, Greeks, underlying)
        │
   ┌────┴─────────────────────┐
   ▼                          ▼
Quant Engine             Portfolio Service
(Deterministic Rules)    (P&L, Positions, Cost Basis)
   │                          │
   ▼                          ▼
Options AI Agent         Fundamental AI Agent
(Sell options ideas)     (EDGAR + DCF + Cash Flow)
   │                          │
   └────────────┬─────────────┘
                ▼
         Risk Management Gate
                │
                ▼
         Postgres (Recommendations, Trades, P&L)
                │
                ▼
         FastAPI Backend (REST + WebSockets)
                │
                ▼
         React Frontend Dashboard
```

---

## Microservices

| Service | Language | Purpose |
|---|---|---|
| `ingestion-service` | Python | Streams Schwab options chain + prices → InfluxDB |
| `quant-engine` | Python | Deterministic IV percentile, skew, spread rules |
| `options-agent` | Python | LLM agent: analyzes quant output, recommends option sells |
| `fundamental-agent` | Python | LLM agent: EDGAR RAG, DCF, cash flow, custom charts |
| `portfolio-service` | Python | Real-time P&L, average cost, premium collected tracking |
| `risk-engine` | Python | Validates margin, exposure limits before display |
| `api-gateway` | Python (FastAPI) | REST + WebSocket endpoints for frontend |
| `frontend` | React + Vite | Dashboard: charts, recommendations, portfolio, settings |
| `worker` | Python (Celery) | Background jobs: EDGAR fetch, DCF compute, scheduled tasks |

---

## Data Stores

| Store | Purpose |
|---|---|
| **InfluxDB** | Options ticks, IV, Greeks, underlying price history (time-series) |
| **Postgres** | Trade recommendations, user positions, P&L history, audit trail |
| **pgvector** | Embedded EDGAR filings for RAG (fundamental agent) |
| **Redis** | Celery broker, WebSocket pub/sub, caching |

---

## Frontend Pages

### 1. `/dashboard` — Live Options Monitor
- Select stocks to stream (add/remove tickers)
- Live options chain table (bid/ask, IV, Greeks, volume, OI)
- Real-time underlying price chart
- WebSocket connection to InfluxDB via API gateway

### 2. `/options-agent` — Options AI Recommendations
- List of AI-generated sell options ideas
- Each idea shows: symbol, strategy, legs, max profit/loss, probability, reasoning, risk flags
- User can mark ideas as taken, ignored, or paper traded
- Refresh / auto-update toggle

### 3. `/fundamental-agent` — Long-Term Stock Analysis
- Select stocks for deep analysis
- Triggers EDGAR RAG + DCF + cash flow computation
- Displays: valuation summary, revenue/earnings charts, DCF output, AI narrative
- Custom fiscal charts (similar to fiscal.ai)

### 4. `/portfolio` — Real-Time P&L
- Pulls live positions from Schwab API
- Shows: position, avg cost (including premium collected), current value, P&L
- Tracks premium collected from sold options to adjust cost basis
- Real-time updates via WebSocket

### 5. `/settings` — Configuration
- Add/remove stocks to stream
- API key management (Schwab)
- Agent parameters (risk tolerance, DTE range, delta range, etc.)

---

## Schwab API Integration

- **Auth**: OAuth2 (already set up by user — do not overwrite credentials)
- **Endpoints used**:
  - `GET /marketdata/v1/chains` — options chain
  - `GET /marketdata/v1/{symbol}/quotes` — real-time stock price
  - `GET /trader/v1/accounts/{accountId}/positions` — portfolio positions
- **Streaming**: Use Schwab's streaming WebSocket API for real-time price updates
- **Rate limits**: Respect Schwab's rate limits; use async + exponential backoff

---

## Options AI Agent

**Input**: Structured JSON from Quant Engine (IV percentile, skew, term structure, etc.)

**Output format** (strict JSON):
```json
{
  "symbol": "NVDA",
  "strategy": "Put Credit Spread",
  "legs": [
    {"action": "SELL", "strike": 850, "type": "PUT", "expiry": "2025-03-21"},
    {"action": "BUY", "strike": 830, "type": "PUT", "expiry": "2025-03-21"}
  ],
  "max_profit": 420,
  "max_loss": 1580,
  "probability_estimate": 0.72,
  "capital_required": 1580,
  "reasoning_summary": "High IV percentile with earnings in 5 days.",
  "risk_flags": ["Earnings event risk"],
  "generated_at": "2025-03-03T16:00:00Z"
}
```

**Rules**:
- AI does NOT calculate Greeks or prices — quant engine does that
- AI reasons on structured quant output only
- All LLM responses must be valid JSON (enforce via system prompt + output parser)
- Focus on high-probability income strategies: credit spreads, cash-secured puts, covered calls, iron condors

---

## Fundamental AI Agent

**Capabilities**:
- RAG over EDGAR filings (10-K, 10-Q) stored in pgvector
- DCF model: project free cash flow, apply discount rate, compute intrinsic value
- Cash flow analysis: operating, investing, financing trends
- Custom charts: revenue growth, margins, EPS trend, debt levels
- AI narrative: plain English summary of thesis + risks

**Output**: Structured report with charts + AI text displayed on `/fundamental-agent` page

---

## Portfolio Service

**Cost Basis Logic**:
```
Adjusted Cost Basis = (Shares × Avg Purchase Price) - Total Premium Collected
Effective Cost Per Share = Adjusted Cost Basis / Shares
```

- Track every sold option premium collected against the underlying stock
- Real-time P&L = Current Market Value - Adjusted Cost Basis
- Pull live prices from Schwab or InfluxDB

---

## Docker Compose Structure

```
docker-compose.yml
services:
  influxdb
  postgres
  redis
  ingestion-service
  quant-engine
  options-agent
  fundamental-agent
  portfolio-service
  risk-engine
  api-gateway
  frontend
  worker (Celery)
```

All services on a shared internal Docker network.
Only `api-gateway` and `frontend` expose ports externally.

---

## Environment Variables

Store all secrets in `.env` (never commit to git):

```
SCHWAB_API_KEY=
SCHWAB_API_SECRET=
SCHWAB_ACCOUNT_ID=
ANTHROPIC_API_KEY=
INFLUXDB_URL=http://influxdb:8086
INFLUXDB_TOKEN=
INFLUXDB_ORG=
INFLUXDB_BUCKET=options
POSTGRES_URL=postgresql://user:pass@postgres:5432/trading
REDIS_URL=redis://redis:6379
```

---

## Implementation Order

Claude should implement in this order:

1. **Docker Compose skeleton** — all services defined, health checks, volumes
2. **InfluxDB + Postgres schemas** — buckets, measurements, tables
3. **Ingestion Service** — Schwab auth, options chain streaming, write to InfluxDB
4. **API Gateway** — FastAPI with WebSocket + REST routes, reads from InfluxDB
5. **Frontend skeleton** — React + Vite, routing, all 5 pages scaffolded
6. **Live Options Chain page** — WebSocket feed, options table, price chart
7. **Quant Engine** — IV percentile, skew calculation
8. **Options AI Agent** — LLM integration, JSON output, recommendations page
9. **Portfolio Service** — Schwab positions, premium tracking, P&L page
10. **Fundamental Agent** — EDGAR fetch, pgvector RAG, DCF, charts page
11. **Risk Engine** — validation layer before displaying recommendations
12. **Settings page** — ticker management, agent config
13. **Polish** — error handling, loading states, mobile responsiveness

---

## Coding Standards

- Python services: use `async/await`, `httpx` for HTTP, `pydantic` for models
- FastAPI: use dependency injection, background tasks for heavy work
- React: functional components, hooks, TailwindCSS for styling
- All LLM calls: wrap in try/catch, validate JSON output, log failures
- InfluxDB writes: batch writes, never write one point at a time
- Never hardcode credentials — always use environment variables
- Every service must have a `/health` endpoint

---

## Key Constraints

- Runs on Raspberry Pi 4/5 — be mindful of memory usage
- Schwab API credentials already configured by user — do not overwrite
- InfluxDB OSS (not cloud) — already installed on the Pi
- AI does NOT directly calculate options prices or Greeks — quant engine only
- Strict JSON enforcement on all LLM outputs
- Full audit trail: every recommendation and outcome must be logged to Postgres

---

## Notes for Claude

- When asked to implement a service, always start with the Dockerfile and requirements.txt
- Always check if a service already exists before creating it
- Prefer incremental, working code over large untested blocks
- Ask for clarification before making changes to Schwab auth code
- When modifying docker-compose.yml, preserve all existing service definitions
