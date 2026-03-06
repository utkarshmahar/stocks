"""IV percentile, rank, and trend computation."""
import numpy as np
import logging

from shared.config import get_settings
from shared.influxdb_client import influx_query

logger = logging.getLogger(__name__)
settings = get_settings()


async def _get_iv_history(symbol: str, days: int = 30) -> list[float]:
    """Fetch historical IV values from InfluxDB, aggregated hourly."""
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


async def _get_current_iv(symbol: str) -> float | None:
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


async def _get_daily_iv(symbol: str, days: int = 5) -> list[float]:
    """Get daily average IV for trend calculation."""
    query = f'''
    from(bucket: "{settings.influxdb_bucket}")
      |> range(start: -{days}d)
      |> filter(fn: (r) => r._measurement == "options_data" and r.symbol == "{symbol}")
      |> filter(fn: (r) => r._field == "implied_volatility")
      |> filter(fn: (r) => r.option_type == "CALL")
      |> aggregateWindow(every: 1d, fn: mean, createEmpty: false)
      |> yield(name: "daily_iv")
    '''
    rows = await influx_query(query)
    return [float(r.get("_value", 0)) for r in rows if r.get("_value")]


async def compute_iv_analysis(symbol: str) -> dict:
    """Compute IV percentile, rank, and trend for a symbol.

    Returns dict with keys:
        iv_percentile, iv_rank, current_iv, iv_trend
    """
    result = {
        "iv_percentile": None,
        "iv_rank": None,
        "current_iv": None,
        "iv_trend": None,
    }

    iv_history = await _get_iv_history(symbol, 30)
    current_iv = await _get_current_iv(symbol)
    result["current_iv"] = current_iv

    if iv_history and current_iv:
        # IV percentile: % of historical values below current
        result["iv_percentile"] = sum(1 for v in iv_history if v < current_iv) / len(iv_history)

        # IV rank: normalized position in min-max range
        iv_min = min(iv_history)
        iv_max = max(iv_history)
        if iv_max > iv_min:
            result["iv_rank"] = (current_iv - iv_min) / (iv_max - iv_min)

    # IV trend: slope of daily IV over 5 days
    daily_iv = await _get_daily_iv(symbol, 5)
    if len(daily_iv) >= 3:
        x = np.arange(len(daily_iv))
        coeffs = np.polyfit(x, daily_iv, 1)
        result["iv_trend"] = round(float(coeffs[0]), 6)

    logger.debug("IV analysis for %s: percentile=%.2f, rank=%.2f, trend=%.6f",
                 symbol,
                 result["iv_percentile"] or 0,
                 result["iv_rank"] or 0,
                 result["iv_trend"] or 0)
    return result
