"""Quant Engine — Pre-computed quant summaries with strategy screening.

Endpoints read from Redis (fast) with fallback to on-demand compute.
A background scheduler computes every 5 minutes during market hours.
"""
import asyncio
import json
import logging

from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager

from shared.config import get_settings
from shared.health import health_router
from shared.influxdb_client import influx_query
from shared.redis_client import get_redis
from shared.models import QuantSummaryV2

from scheduler import scheduler_loop, run_compute_cycle, compute_symbol

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the background scheduler on app startup."""
    task = asyncio.create_task(scheduler_loop())
    logger.info("Scheduler task started")
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Quant Engine", lifespan=lifespan)
app.include_router(health_router)


@app.get("/api/quant/{symbol}/summary")
async def quant_summary(symbol: str):
    """Get quant summary for a symbol. Reads from Redis, falls back to on-demand compute."""
    symbol = symbol.upper()
    redis = await get_redis()
    cached = await redis.get(f"quant:{symbol}")

    if cached:
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            pass

    # Fallback: compute on demand
    logger.info("Cache miss for %s, computing on demand", symbol)
    result = await compute_symbol(symbol)
    if result is None:
        raise HTTPException(404, f"No data for {symbol}")

    result.source = "on_demand"
    # Store in Redis for subsequent requests
    await redis.setex(f"quant:{symbol}", 600, result.model_dump_json())
    return result.model_dump()


@app.get("/api/quant/all")
async def quant_all():
    """Get all cached quant summaries from Redis."""
    redis = await get_redis()
    keys = []
    async for key in redis.scan_iter(match="quant:*"):
        keys.append(key)

    results = []
    if keys:
        values = await redis.mget(keys)
        for val in values:
            if val:
                try:
                    results.append(json.loads(val))
                except json.JSONDecodeError:
                    pass

    return results


@app.post("/api/quant/refresh")
async def quant_refresh():
    """Force recompute for all watchlist symbols."""
    logger.info("Manual refresh triggered")
    computed = await run_compute_cycle()
    return {"status": "ok", "symbols_computed": computed}


@app.get("/api/quant/{symbol}/iv-history")
async def iv_history_endpoint(symbol: str, days: int = 30):
    """Get raw IV history from InfluxDB (unchanged from v1)."""
    query = f'''
    from(bucket: "{settings.influxdb_bucket}")
      |> range(start: -{days}d)
      |> filter(fn: (r) => r._measurement == "options_data" and r.symbol == "{symbol.upper()}")
      |> filter(fn: (r) => r._field == "implied_volatility")
      |> filter(fn: (r) => r.option_type == "CALL")
      |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
      |> yield(name: "iv_history")
    '''
    rows = await influx_query(query)
    iv_values = [float(r.get("_value", 0)) for r in rows if r.get("_value")]
    return {"symbol": symbol.upper(), "days": days, "iv_values": iv_values}
