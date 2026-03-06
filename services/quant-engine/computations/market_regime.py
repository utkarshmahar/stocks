"""Market regime: VIX level, expected weekly move from ATM straddle."""
import logging

from shared.config import get_settings
from shared.influxdb_client import influx_query

logger = logging.getLogger(__name__)
settings = get_settings()


async def _get_atm_straddle_price(symbol: str, current_price: float) -> float | None:
    """Get ATM straddle price from nearest weekly expiry.

    Finds the call and put closest to current price with shortest DTE,
    and sums their bid prices as the expected move estimate.
    """
    # Get options near ATM with shortest DTE
    query = f'''
    from(bucket: "{settings.influxdb_bucket}")
      |> range(start: -5m)
      |> filter(fn: (r) => r._measurement == "options_data" and r.symbol == "{symbol}")
      |> filter(fn: (r) => r._field == "bid" or r._field == "strike" or r._field == "days_to_expiration")
      |> last()
      |> pivot(rowKey: ["_time", "option_type", "expiration", "strike"], columnKey: ["_field"], valueColumn: "_value")
      |> sort(columns: ["days_to_expiration"])
    '''
    rows = await influx_query(query)
    if not rows:
        return None

    # Find nearest expiry
    min_dte = None
    for r in rows:
        dte = r.get("days_to_expiration")
        if dte:
            dte_val = int(float(dte))
            if dte_val > 0 and (min_dte is None or dte_val < min_dte):
                min_dte = dte_val

    if min_dte is None:
        return None

    # Filter to nearest expiry, find ATM strike
    nearest = [r for r in rows if r.get("days_to_expiration") and int(float(r["days_to_expiration"])) == min_dte]
    if not nearest:
        return None

    # Find strike closest to current price
    best_strike = None
    best_diff = float("inf")
    for r in nearest:
        strike = r.get("strike")
        if strike:
            diff = abs(float(strike) - current_price)
            if diff < best_diff:
                best_diff = diff
                best_strike = float(strike)

    if best_strike is None:
        return None

    # Sum call bid + put bid at that strike
    call_bid = 0.0
    put_bid = 0.0
    for r in nearest:
        strike = r.get("strike")
        if strike and float(strike) == best_strike:
            bid = float(r.get("bid", 0))
            if r.get("option_type") == "CALL":
                call_bid = bid
            elif r.get("option_type") == "PUT":
                put_bid = bid

    straddle = call_bid + put_bid
    return straddle if straddle > 0 else None


async def _get_vix_level() -> float | None:
    """Try to get VIX level from InfluxDB (stored by ingestion if available)."""
    query = f'''
    from(bucket: "{settings.influxdb_bucket}")
      |> range(start: -1h)
      |> filter(fn: (r) => r._measurement == "stock_quote" and r.symbol == "$VIX.X")
      |> filter(fn: (r) => r._field == "price")
      |> last()
    '''
    rows = await influx_query(query)
    if rows:
        val = rows[0].get("_value")
        if val:
            return float(val)
    return None


async def compute_market_regime(symbol: str, current_price: float) -> dict:
    """Compute market regime metrics.

    Returns dict with keys:
        vix_level, expected_weekly_move, expected_move_pct
    """
    result = {
        "vix_level": None,
        "expected_weekly_move": None,
        "expected_move_pct": None,
    }

    result["vix_level"] = await _get_vix_level()

    straddle = await _get_atm_straddle_price(symbol, current_price)
    if straddle and current_price > 0:
        result["expected_weekly_move"] = round(straddle, 2)
        result["expected_move_pct"] = round((straddle / current_price) * 100, 2)

    logger.debug("Market regime for %s: vix=%.1f, exp_move=$%.2f (%.2f%%)",
                 symbol,
                 result["vix_level"] or 0,
                 result["expected_weekly_move"] or 0,
                 result["expected_move_pct"] or 0)
    return result
