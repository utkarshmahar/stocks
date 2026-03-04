# Options Trading Platform — Custom Skills

## /dev

**Development helper for the options trading platform.**

Automatically loads project context (CLAUDE.md, architecture, current state) and provides quick commands to rebuild and restart Docker services after code changes.

### Usage

```
/dev rebuild <service>    # Rebuild Docker image and restart service
/dev restart <service>    # Restart running service without rebuild
/dev logs <service>       # Show last 50 lines of service logs
/dev status              # Show status of all containers
/dev help                # Show available services
```

### Examples

- `/dev rebuild frontend` — Rebuild frontend after changing Dashboard.tsx
- `/dev rebuild api` — Rebuild API gateway after changing routes
- `/dev restart ingestion-service` — Restart ingestion-service (code already in container)
- `/dev logs api-gateway` — Tail API gateway logs
- `/dev status` — Check health of all 9 services

### Service Aliases

| Alias | Container | Port | Purpose |
|-------|-----------|------|---------|
| `frontend` | stocks-frontend-1 | 3001 | React dashboard (nginx) |
| `api` | stocks-api-gateway-1 | 8000 | FastAPI backend |
| `ingestion` | stocks-ingestion-service-1 | 8010 | Schwab data streaming |
| `quant` | stocks-quant-engine-1 | 8020 | IV/Greeks calculation |
| `options-agent` | stocks-options-agent-1 | 8030 | LLM recommendations |
| `portfolio` | stocks-portfolio-service-1 | 8040 | P&L tracking |
| `risk` | stocks-risk-engine-1 | 8050 | Validation layer |
| `fundamental` | stocks-fundamental-agent-1 | 8060 | DCF + EDGAR analysis |
| `worker` | stocks-worker-1 | N/A | Celery background jobs |

### What it knows

- **CLAUDE.md**: Full system architecture, microservices, data flows
- **Current state**: Running containers, recent commits, pending work
- **Docker stack**: All 9 services, build dependencies, restart strategies
- **Frontend**: Knows to clear browser cache (hard refresh) after frontend rebuilds
- **Memory**: Reads and updates project memory across sessions

### After using /dev rebuild

When you rebuild frontend or services:
1. Docker image is rebuilt with latest code
2. Container is recreated/restarted
3. Service becomes available at its port
4. For frontend: hard refresh your browser (`Ctrl+Shift+R` or `Cmd+Shift+R`)

### Workflow

Typical edit → rebuild → verify cycle:

```
1. Edit /frontend/src/pages/Dashboard.tsx
2. Run: /dev rebuild frontend
3. Hard refresh browser → see changes live
4. Run: /dev status (check health)
```

---

## /monitor

**Quick access to the stack monitor dashboard.**

Starts or shows the native monitoring service that tracks:
- Docker container status
- Schwab token expiry countdown
- Service health endpoints
- InfluxDB status

### Usage

```
/monitor start     # Start monitor.py if not running
/monitor stop      # Stop the monitor
/monitor url       # Show access URL
/monitor status    # Check if running
```

Access at: `http://192.168.0.33:8888`

---

