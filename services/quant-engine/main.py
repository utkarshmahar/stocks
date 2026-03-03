"""Quant Engine — Deterministic IV percentile, skew, term structure analysis."""
import numpy as np
from datetime import datetime

from fastapi import FastAPI, HTTPException

from shared.config import get_settings
from shared.health import health_router
from shared.influxdb_client import influx_query
from shared.models import QuantSummary

app = FastAPI(title="Quant Engine")
app.include_router(health_router)

settings = get_settings()


async def get_iv_history(symbol: str, days: int = 30) -> list[float]:
    """Get historical IV values from InfluxDB."""
    query = f'''
    from(bucket: "{settings.influxdb_bucket}")
      |> range(start: -{days}d)
      |> filter(fn: (r) => r._measurement == "options_data" and r.symbol == "{symbol}")
      |> filter(fn: (r) => r._field == "implied_volatility")
      |> filter(fn: (r) => r.option_type == "CALL")
      |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
      |> yield(name: "iv_history")
    '''
    rows = await influx_query(query)
    return [float(r.get("_value", 0)) for r in rows if r.get("_value")]


async def get_current_iv(symbol: str) -> float | None:
    """Get current average IV for ATM options."""
    query = f'''
    from(bucket: "{settings.influxdb_bucket}")
      |> range(start: -5m)
      |> filter(fn: (r) => r._measurement == "options_data" and r.symbol == "{symbol}")
      |> filter(fn: (r) => r._field == "implied_volatility")
      |> last()
      |> mean()
    '''
    rows = await influx_query(query)
    if rows:
        val = rows[0].get("_value")
        return float(val) if val else None
    return None


async def get_put_call_data(symbol: str) -> dict:
    """Get latest put and call IV for skew calculation."""
    query = f'''
    from(bucket: "{settings.influxdb_bucket}")
      |> range(start: -5m)
      |> filter(fn: (r) => r._measurement == "options_data" and r.symbol == "{symbol}")
      |> filter(fn: (r) => r._field == "implied_volatility")
      |> last()
      |> group(columns: ["option_type"])
      |> mean()
    '''
    rows = await influx_query(query)
    result = {}
    for r in rows:
        otype = r.get("option_type", "")
        val = r.get("_value")
        if val:
            result[otype] = float(val)
    return result


async def get_volume_oi(symbol: str) -> dict:
    """Get volume and open interest for unusual activity detection."""
    query = f'''
    from(bucket: "{settings.influxdb_bucket}")
      |> range(start: -5m)
      |> filter(fn: (r) => r._measurement == "options_data" and r.symbol == "{symbol}")
      |> filter(fn: (r) => r._field == "volume" or r._field == "open_interest")
      |> last()
      |> sum()
    '''
    rows = await influx_query(query)
    result = {"volume": 0, "open_interest": 0}
    for r in rows:
        field = r.get("_field", "")
        val = r.get("_value")
        if field in result and val:
            result[field] = int(float(val))
    return result


async def get_current_price(symbol: str) -> float:
    """Get current underlying price."""
    query = f'''
    from(bucket: "{settings.influxdb_bucket}")
      |> range(start: -5m)
      |> filter(fn: (r) => r._measurement == "stock_quote" and r.symbol == "{symbol}")
      |> filter(fn: (r) => r._field == "price")
      |> last()
    '''
    rows = await influx_query(query)
    if rows:
        val = rows[0].get("_value")
        if val:
            return float(val)
    return 0.0


@app.get("/api/quant/{symbol}/summary", response_model=QuantSummary)
async def quant_summary(symbol: str):
    symbol = symbol.upper()
    price = await get_current_price(symbol)
    if price == 0:
        raise HTTPException(404, f"No data for {symbol}")

    # IV Percentile (30-day)
    iv_history = await get_iv_history(symbol, 30)
    current_iv = await get_current_iv(symbol)
    iv_percentile = None
    iv_rank = None
    if iv_history and current_iv:
        iv_percentile = sum(1 for v in iv_history if v < current_iv) / len(iv_history)
        iv_min = min(iv_history)
        iv_max = max(iv_history)
        if iv_max > iv_min:
            iv_rank = (current_iv - iv_min) / (iv_max - iv_min)

    # Put/Call skew
    pc_data = await get_put_call_data(symbol)
    put_call_skew = None
    if "PUT" in pc_data and "CALL" in pc_data and pc_data["CALL"] > 0:
        put_call_skew = pc_data["PUT"] / pc_data["CALL"]

    # Volume/OI ratio
    vol_oi = await get_volume_oi(symbol)
    vol_oi_ratio = None
    unusual = False
    if vol_oi["open_interest"] > 0:
        vol_oi_ratio = vol_oi["volume"] / vol_oi["open_interest"]
        unusual = vol_oi_ratio > 1.5

    return QuantSummary(
        symbol=symbol,
        current_price=price,
        iv_percentile=iv_percentile,
        iv_rank=iv_rank,
        put_call_skew=put_call_skew,
        unusual_activity=unusual,
        volume_oi_ratio=vol_oi_ratio,
    )


@app.get("/api/quant/{symbol}/iv-history")
async def iv_history_endpoint(symbol: str, days: int = 30):
    history = await get_iv_history(symbol.upper(), days)
    return {"symbol": symbol.upper(), "days": days, "iv_values": history}
