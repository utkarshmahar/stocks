"""Volume/OI analysis, put/call skew, unusual activity detection."""
import logging

from shared.config import get_settings
from shared.influxdb_client import influx_query

logger = logging.getLogger(__name__)
settings = get_settings()


async def _get_put_call_iv(symbol: str) -> dict:
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


async def _get_volume_oi_by_type(symbol: str) -> dict:
    """Get volume and OI broken down by option type."""
    query = f'''
    from(bucket: "{settings.influxdb_bucket}")
      |> range(start: -5m)
      |> filter(fn: (r) => r._measurement == "options_data" and r.symbol == "{symbol}")
      |> filter(fn: (r) => r._field == "volume" or r._field == "open_interest")
      |> last()
      |> group(columns: ["option_type", "_field"])
      |> sum()
    '''
    rows = await influx_query(query)
    result = {
        "call_volume": 0, "put_volume": 0,
        "call_oi": 0, "put_oi": 0,
    }
    for r in rows:
        otype = r.get("option_type", "")
        field = r.get("_field", "")
        val = r.get("_value")
        if not val:
            continue
        v = int(float(val))
        if otype == "CALL" and field == "volume":
            result["call_volume"] = v
        elif otype == "PUT" and field == "volume":
            result["put_volume"] = v
        elif otype == "CALL" and field == "open_interest":
            result["call_oi"] = v
        elif otype == "PUT" and field == "open_interest":
            result["put_oi"] = v
    return result


async def compute_flow_analysis(symbol: str) -> dict:
    """Compute flow metrics: skew, volume/OI, unusual activity.

    Returns dict with keys:
        put_call_skew, volume_oi_ratio, unusual_activity,
        total_call_volume, total_put_volume, total_call_oi, total_put_oi
    """
    result = {
        "put_call_skew": None,
        "volume_oi_ratio": None,
        "unusual_activity": False,
        "total_call_volume": 0,
        "total_put_volume": 0,
        "total_call_oi": 0,
        "total_put_oi": 0,
    }

    # Put/Call IV skew
    pc_iv = await _get_put_call_iv(symbol)
    if "PUT" in pc_iv and "CALL" in pc_iv and pc_iv["CALL"] > 0:
        result["put_call_skew"] = round(pc_iv["PUT"] / pc_iv["CALL"], 4)

    # Volume/OI by type
    vol_oi = await _get_volume_oi_by_type(symbol)
    result["total_call_volume"] = vol_oi["call_volume"]
    result["total_put_volume"] = vol_oi["put_volume"]
    result["total_call_oi"] = vol_oi["call_oi"]
    result["total_put_oi"] = vol_oi["put_oi"]

    total_vol = vol_oi["call_volume"] + vol_oi["put_volume"]
    total_oi = vol_oi["call_oi"] + vol_oi["put_oi"]
    if total_oi > 0:
        result["volume_oi_ratio"] = round(total_vol / total_oi, 4)
        result["unusual_activity"] = result["volume_oi_ratio"] > 1.5

    logger.debug("Flow analysis for %s: skew=%.3f, vol_oi=%.3f, unusual=%s",
                 symbol,
                 result["put_call_skew"] or 0,
                 result["volume_oi_ratio"] or 0,
                 result["unusual_activity"])
    return result
