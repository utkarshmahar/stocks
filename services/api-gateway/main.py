"""API Gateway — REST + WebSocket endpoints for the frontend."""
import asyncio
import json
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import get_settings
from shared.health import health_router
from shared.influxdb_client import influx_query
from shared.postgres import get_db
from shared.redis_client import get_redis

app = FastAPI(title="Options Trading API Gateway")
app.include_router(health_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

settings = get_settings()


# ---- Watchlist ----

@app.get("/api/watchlist")
async def get_watchlist(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT id, symbol, active, added_at FROM watchlist ORDER BY id")
    )
    rows = result.fetchall()
    return [
        {"id": r[0], "symbol": r[1], "active": r[2], "added_at": r[3].isoformat() if r[3] else None}
        for r in rows
    ]


@app.post("/api/watchlist")
async def add_to_watchlist(payload: dict, db: AsyncSession = Depends(get_db)):
    symbol = payload.get("symbol", "").upper().strip()
    if not symbol:
        raise HTTPException(400, "Symbol required")
    await db.execute(
        text("INSERT INTO watchlist (symbol) VALUES (:s) ON CONFLICT (symbol) DO UPDATE SET active = TRUE"),
        {"s": symbol},
    )
    await db.commit()
    return {"symbol": symbol, "status": "added"}


@app.delete("/api/watchlist/{symbol}")
async def remove_from_watchlist(symbol: str, db: AsyncSession = Depends(get_db)):
    await db.execute(
        text("UPDATE watchlist SET active = FALSE WHERE symbol = :s"),
        {"s": symbol.upper()},
    )
    await db.commit()
    return {"symbol": symbol.upper(), "status": "removed"}


# ---- Live Quotes from InfluxDB ----

@app.get("/api/quote/{symbol}")
async def get_quote(symbol: str):
    query = f'''
    from(bucket: "{settings.influxdb_bucket}")
      |> range(start: -1d)
      |> filter(fn: (r) => r._measurement == "stock_quote" and r.symbol == "{symbol.upper()}")
      |> last()
      |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''
    rows = await influx_query(query)
    if not rows:
        raise HTTPException(404, f"No quote data for {symbol}")
    row = rows[-1]
    return {
        "symbol": symbol.upper(),
        "price": float(row.get("price", 0)),
        "bid": float(row.get("bid", 0)),
        "ask": float(row.get("ask", 0)),
        "change": float(row.get("change", 0)),
        "percent_change": float(row.get("percent_change", 0)),
        "volume": int(float(row.get("volume", 0))),
        "high": float(row.get("high", 0)),
        "low": float(row.get("low", 0)),
        "open": float(row.get("open", 0)),
        "timestamp": row.get("_time"),
    }


@app.get("/api/options/{symbol}")
async def get_options(symbol: str):
    query = f'''
    from(bucket: "{settings.influxdb_bucket}")
      |> range(start: -1d)
      |> filter(fn: (r) => r._measurement == "options_data" and r.symbol == "{symbol.upper()}")
      |> last()
      |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''
    rows = await influx_query(query)
    calls = []
    puts = []
    for row in rows:
        contract = {
            "strike": float(row.get("strike", 0)),
            "expiration": row.get("expiration", ""),
            "bid": float(row.get("bid", 0)),
            "ask": float(row.get("ask", 0)),
            "last": float(row.get("last", 0)),
            "mark": float(row.get("mark", 0)),
            "volume": int(float(row.get("volume", 0))),
            "open_interest": int(float(row.get("open_interest", 0))),
            "iv": float(row.get("implied_volatility", 0)),
            "delta": float(row.get("delta", 0)),
            "gamma": float(row.get("gamma", 0)),
            "theta": float(row.get("theta", 0)),
            "vega": float(row.get("vega", 0)),
            "dte": int(float(row.get("days_to_expiration", 0))),
            "itm": row.get("in_the_money", "false") == "true",
        }
        if row.get("option_type") == "CALL":
            calls.append(contract)
        else:
            puts.append(contract)

    return {"symbol": symbol.upper(), "calls": calls, "puts": puts}


# ---- Recommendations ----

@app.get("/api/recommendations")
async def get_recommendations(
    status: str | None = None, symbol: str | None = None, db: AsyncSession = Depends(get_db)
):
    q = "SELECT * FROM recommendations WHERE 1=1"
    params = {}
    if status:
        q += " AND status = :status"
        params["status"] = status
    if symbol:
        q += " AND symbol = :symbol"
        params["symbol"] = symbol.upper()
    q += " ORDER BY generated_at DESC LIMIT 50"
    result = await db.execute(text(q), params)
    rows = result.fetchall()
    columns = result.keys()
    return [dict(zip(columns, row)) for row in rows]


@app.patch("/api/recommendations/{rec_id}")
async def update_recommendation(rec_id: int, payload: dict, db: AsyncSession = Depends(get_db)):
    status = payload.get("status")
    if status not in ("taken", "ignored", "paper_traded", "pending"):
        raise HTTPException(400, "Invalid status")
    await db.execute(
        text("UPDATE recommendations SET status = :s, resolved_at = NOW() WHERE id = :id"),
        {"s": status, "id": rec_id},
    )
    await db.commit()
    return {"id": rec_id, "status": status}


# ---- Portfolio ----

@app.get("/api/portfolio/positions")
async def get_positions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT * FROM positions ORDER BY symbol"))
    rows = result.fetchall()
    columns = result.keys()
    return [dict(zip(columns, row)) for row in rows]


@app.get("/api/portfolio/premium")
async def get_premium_collections(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT * FROM premium_collections ORDER BY created_at DESC LIMIT 50")
    )
    rows = result.fetchall()
    columns = result.keys()
    return [dict(zip(columns, row)) for row in rows]


# ---- Fundamental ----

@app.get("/api/fundamental/{symbol}")
async def get_fundamental_report(symbol: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT * FROM fundamental_reports WHERE symbol = :s ORDER BY created_at DESC LIMIT 1"),
        {"s": symbol.upper()},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(404, f"No report for {symbol}")
    columns = result.keys()
    return dict(zip(columns, row))


# ---- Agent Config ----

@app.get("/api/config")
async def get_config(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT key, value, description FROM agent_config ORDER BY key"))
    rows = result.fetchall()
    config = {}
    for row in rows:
        val = row[1]
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                pass
        config[row[0]] = {"value": val, "description": row[2]}
    return config


@app.put("/api/config/{key}")
async def update_config(key: str, payload: dict, db: AsyncSession = Depends(get_db)):
    value = payload.get("value")
    await db.execute(
        text("UPDATE agent_config SET value = :v, updated_at = NOW() WHERE key = :k"),
        {"v": json.dumps(value), "k": key},
    )
    await db.commit()
    return {"key": key, "value": value}


# ---- Quant Engine Proxy (reads from Redis) ----

@app.get("/api/quant/{symbol}/summary")
async def get_quant_summary(symbol: str):
    """Proxy quant summary from Redis (avoids frontend needing quant-engine port)."""
    redis = await get_redis()
    cached = await redis.get(f"quant:{symbol.upper()}")
    if cached:
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            pass
    raise HTTPException(404, f"No quant data for {symbol}. Quant engine may not have computed yet.")


@app.get("/api/quant/all")
async def get_all_quant_summaries():
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


# ---- Service Health Overview ----

@app.get("/api/services/health")
async def services_health():
    """Check health of all backend services."""
    import httpx

    services = {
        "ingestion": "http://ingestion-service:8010/health",
        "quant-engine": "http://quant-engine:8020/health",
        "options-agent": "http://options-agent:8030/health",
        "portfolio": "http://portfolio-service:8040/health",
        "risk-engine": "http://risk-engine:8050/health",
        "fundamental": "http://fundamental-agent:8060/health",
    }
    results = {}
    async with httpx.AsyncClient(timeout=3.0) as client:
        for name, url in services.items():
            try:
                resp = await client.get(url)
                results[name] = "healthy" if resp.status_code == 200 else "unhealthy"
            except Exception:
                results[name] = "unavailable"
    return results


# ---- Stock Price History (intraday) ----

@app.get("/api/history/stock-price")
async def get_stock_price_history(symbol: str, time_range: str = "1d"):
    flux_range = {"1d": "-1d", "3d": "-3d", "1w": "-7d", "1m": "-30d"}.get(time_range, "-1d")
    aggregate = ""
    if time_range == "1m":
        aggregate = '|> aggregateWindow(every: 1h, fn: mean, createEmpty: false)'
    elif time_range == "1w":
        aggregate = '|> aggregateWindow(every: 15m, fn: mean, createEmpty: false)'

    query = f'''
    from(bucket: "{settings.influxdb_bucket}")
      |> range(start: {flux_range})
      |> filter(fn: (r) => r._measurement == "stock_quote" and r.symbol == "{symbol.upper()}" and r._field == "price")
      {aggregate}
      |> sort(columns: ["_time"])
    '''
    rows = await influx_query(query)
    return [
        {"time": r["_time"], "price": float(r["_value"])}
        for r in rows if r.get("_value") is not None
    ]


# ---- Greek History ----

GREEK_FIELD_MAP = {
    "iv": "implied_volatility",
    "delta": "delta",
    "gamma": "gamma",
    "theta": "theta",
}

TIME_RANGE_MAP = {
    "1d": "-1d",
    "3d": "-3d",
    "1w": "-7d",
    "1m": "-30d",
}


@app.get("/api/history/greek")
async def get_greek_history(
    symbol: str,
    option_type: str,
    expiration: str,
    strike: float,
    greek: str,
    time_range: str = "1d",
):
    field = GREEK_FIELD_MAP.get(greek)
    if not field:
        raise HTTPException(400, f"Invalid greek: {greek}. Use: iv, delta, gamma, theta")
    flux_range = TIME_RANGE_MAP.get(time_range, "-1d")
    strike_str = str(strike)

    # Aggregate for longer ranges to reduce data volume on Pi
    aggregate = ""
    if time_range in ("1w", "1m"):
        window = "1h" if time_range == "1m" else "15m"
        aggregate = f'|> aggregateWindow(every: {window}, fn: mean, createEmpty: false)'

    greek_query = f'''
    from(bucket: "{settings.influxdb_bucket}")
      |> range(start: {flux_range})
      |> filter(fn: (r) => r._measurement == "options_data")
      |> filter(fn: (r) => r.symbol == "{symbol.upper()}")
      |> filter(fn: (r) => r.option_type == "{option_type.upper()}")
      |> filter(fn: (r) => r.expiration == "{expiration}")
      |> filter(fn: (r) => r.strike == "{strike_str}")
      |> filter(fn: (r) => r._field == "{field}")
      {aggregate}
      |> sort(columns: ["_time"])
    '''

    price_query = f'''
    from(bucket: "{settings.influxdb_bucket}")
      |> range(start: {flux_range})
      |> filter(fn: (r) => r._measurement == "stock_quote")
      |> filter(fn: (r) => r.symbol == "{symbol.upper()}")
      |> filter(fn: (r) => r._field == "price")
      {aggregate}
      |> sort(columns: ["_time"])
    '''

    greek_rows, price_rows = await asyncio.gather(
        influx_query(greek_query),
        influx_query(price_query),
    )

    greek_history = [
        {"time": r["_time"], "value": float(r["_value"])}
        for r in greek_rows if r.get("_value") is not None
    ]
    price_history = [
        {"time": r["_time"], "value": float(r["_value"])}
        for r in price_rows if r.get("_value") is not None
    ]

    return {
        "contract": {
            "symbol": symbol.upper(),
            "strike": strike,
            "expiration": expiration,
            "option_type": option_type.upper(),
            "greek": greek,
        },
        "greek_history": greek_history,
        "price_history": price_history,
    }


# ---- Option Price History (Bid/Ask/Last) ----

@app.get("/api/history/option-price")
async def get_option_price_history(
    symbol: str,
    option_type: str,
    expiration: str,
    strike: float,
    time_range: str = "1d",
):
    flux_range = TIME_RANGE_MAP.get(time_range, "-1d")
    strike_str = str(strike)

    aggregate = ""
    if time_range in ("1w", "1m"):
        window = "1h" if time_range == "1m" else "15m"
        aggregate = f'|> aggregateWindow(every: {window}, fn: mean, createEmpty: false)'

    def make_field_query(field: str) -> str:
        return f'''
        from(bucket: "{settings.influxdb_bucket}")
          |> range(start: {flux_range})
          |> filter(fn: (r) => r._measurement == "options_data")
          |> filter(fn: (r) => r.symbol == "{symbol.upper()}")
          |> filter(fn: (r) => r.option_type == "{option_type.upper()}")
          |> filter(fn: (r) => r.expiration == "{expiration}")
          |> filter(fn: (r) => r.strike == "{strike_str}")
          |> filter(fn: (r) => r._field == "{field}")
          {aggregate}
          |> sort(columns: ["_time"])
        '''

    stock_query = f'''
    from(bucket: "{settings.influxdb_bucket}")
      |> range(start: {flux_range})
      |> filter(fn: (r) => r._measurement == "stock_quote")
      |> filter(fn: (r) => r.symbol == "{symbol.upper()}")
      |> filter(fn: (r) => r._field == "price")
      {aggregate}
      |> sort(columns: ["_time"])
    '''

    bid_rows, ask_rows, last_rows, stock_rows = await asyncio.gather(
        influx_query(make_field_query("bid")),
        influx_query(make_field_query("ask")),
        influx_query(make_field_query("last")),
        influx_query(stock_query),
    )

    def to_series(rows):
        return [{"time": r["_time"], "value": float(r["_value"])} for r in rows if r.get("_value") is not None]

    return {
        "contract": {
            "symbol": symbol.upper(),
            "strike": strike,
            "expiration": expiration,
            "option_type": option_type.upper(),
        },
        "bid_history": to_series(bid_rows),
        "ask_history": to_series(ask_rows),
        "last_history": to_series(last_rows),
        "price_history": to_series(stock_rows),
    }


# ---- WebSocket: Live Options Updates ----

@app.websocket("/ws/options")
async def websocket_options(websocket: WebSocket):
    await websocket.accept()
    redis = await get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe("options:updates")
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message["type"] == "message":
                await websocket.send_text(message["data"])
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe("options:updates")
        await pubsub.close()
