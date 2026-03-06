"""Scan InfluxDB for nearest weekly option chain to feed strategy screeners."""
import logging

from shared.config import get_settings
from shared.influxdb_client import influx_query

logger = logging.getLogger(__name__)
settings = get_settings()


async def scan_strikes(symbol: str) -> dict:
    """Fetch the nearest weekly chain from InfluxDB.

    Returns dict with keys:
        calls: list[dict]  — each with strike, expiration, bid, ask, delta, volume, oi, dte, iv
        puts: list[dict]
        nearest_expiry: str
        dte: int
    """
    # Fetch all recent option data pivoted
    query = f'''
    from(bucket: "{settings.influxdb_bucket}")
      |> range(start: -5m)
      |> filter(fn: (r) => r._measurement == "options_data" and r.symbol == "{symbol}")
      |> filter(fn: (r) =>
          r._field == "bid" or r._field == "ask" or r._field == "delta" or
          r._field == "volume" or r._field == "open_interest" or
          r._field == "days_to_expiration" or r._field == "implied_volatility" or
          r._field == "strike"
      )
      |> last()
      |> pivot(rowKey: ["_time", "option_type", "expiration", "strike"], columnKey: ["_field"], valueColumn: "_value")
    '''
    rows = await influx_query(query)
    if not rows:
        return {"calls": [], "puts": [], "nearest_expiry": None, "dte": None}

    # Find nearest expiry with DTE > 0
    min_dte = None
    nearest_expiry = None
    for r in rows:
        dte_val = r.get("days_to_expiration")
        if dte_val:
            dte = int(float(dte_val))
            if dte > 0 and (min_dte is None or dte < min_dte):
                min_dte = dte
                nearest_expiry = r.get("expiration")

    if min_dte is None:
        return {"calls": [], "puts": [], "nearest_expiry": None, "dte": None}

    # Filter to nearest expiry and build strike lists
    calls = []
    puts = []
    for r in rows:
        dte_val = r.get("days_to_expiration")
        if not dte_val or int(float(dte_val)) != min_dte:
            continue

        strike_data = {
            "strike": float(r.get("strike", 0)),
            "expiration": r.get("expiration", ""),
            "bid": float(r.get("bid", 0)),
            "ask": float(r.get("ask", 0)),
            "delta": float(r.get("delta", 0)),
            "volume": int(float(r.get("volume", 0))),
            "open_interest": int(float(r.get("open_interest", 0))),
            "dte": min_dte,
            "iv": float(r.get("implied_volatility", 0)),
        }

        if r.get("option_type") == "CALL":
            calls.append(strike_data)
        elif r.get("option_type") == "PUT":
            puts.append(strike_data)

    # Sort by strike
    calls.sort(key=lambda x: x["strike"])
    puts.sort(key=lambda x: x["strike"])

    logger.debug("Strike scan for %s: %d calls, %d puts, expiry=%s (DTE=%d)",
                 symbol, len(calls), len(puts), nearest_expiry, min_dte)
    return {
        "calls": calls,
        "puts": puts,
        "nearest_expiry": nearest_expiry,
        "dte": min_dte,
    }
