"""Ingestion Service — Streams Schwab options chain data to InfluxDB."""
import asyncio
import json
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from schwab.client import Client

from shared.config import get_settings
from shared.health import health_router
from shared.schwab_auth import get_schwab_client
from shared.influxdb_client import influx_write
from shared.redis_client import get_redis
from shared.postgres import get_session_factory

app = FastAPI(title="Ingestion Service")
app.include_router(health_router)

settings = get_settings()


async def get_watchlist_symbols() -> list[str]:
    """Load active symbols from Postgres watchlist, fallback to env."""
    try:
        factory = get_session_factory()
        async with factory() as session:
            from sqlalchemy import text
            result = await session.execute(
                text("SELECT symbol FROM watchlist WHERE active = TRUE")
            )
            symbols = [row[0] for row in result.fetchall()]
            if symbols:
                return symbols
    except Exception:
        pass
    return settings.symbols_list


ET = ZoneInfo("America/New_York")


def is_normal_trading_hours() -> bool:
    """Check if current time is within normal trading hours (9:30 AM - 4:00 PM ET).

    Options data is only written to InfluxDB during these hours.
    Excludes weekends and US market holidays.
    """
    now = datetime.now(tz=ET)
    weekday = now.weekday()  # 0=Monday, 6=Sunday

    # Skip weekends
    if weekday >= 5:  # Saturday or Sunday
        return False

    # Check time: 9:30 AM - 4:00 PM
    hour, minute = now.hour, now.minute
    start = (9, 30)  # 9:30 AM
    end = (16, 0)    # 4:00 PM

    current = (hour, minute)
    return start <= current < end


def is_extended_trading_hours() -> bool:
    """Check if current time is within extended trading hours (4:00 AM - 8:00 PM ET).

    Stock prices are written to InfluxDB during these hours.
    Excludes weekends and US market holidays.
    """
    now = datetime.now(tz=ET)
    weekday = now.weekday()  # 0=Monday, 6=Sunday

    # Skip weekends
    if weekday >= 5:  # Saturday or Sunday
        return False

    # Check time: 4:00 AM - 8:00 PM
    hour, minute = now.hour, now.minute
    start = (4, 0)   # 4:00 AM (pre-market)
    end = (20, 0)    # 8:00 PM (after-hours)

    current = (hour, minute)
    return start <= current < end


def query_options_chain(client, symbol: str) -> dict | None:
    """Query Schwab for options chain data."""
    try:
        response = client.get_option_chain(
            symbol,
            contract_type=Client.Options.ContractType.ALL,
            strike_count=settings.strike_count,
            include_underlying_quote=True,
        )
        if response.status_code == 200:
            return response.json()
        print(f"[WARN] {symbol}: HTTP {response.status_code}")
        return None
    except Exception as e:
        print(f"[ERROR] {symbol}: {e}")
        return None


def filter_by_trading_hours(lines: list[str]) -> list[str]:
    """Filter line protocol based on trading hours.

    - Options data: only during normal trading hours (9:30 AM - 4:00 PM ET)
    - Stock prices: only during extended hours (4:00 AM - 8:00 PM ET)
    """
    normal_hours = is_normal_trading_hours()
    extended_hours = is_extended_trading_hours()

    filtered = []
    for line in lines:
        # Options data: only write during normal trading hours
        if "options_data" in line:
            if normal_hours:
                filtered.append(line)
        # Stock quotes: only write during extended hours
        elif "stock_quote" in line:
            if extended_hours:
                filtered.append(line)
        else:
            filtered.append(line)

    return filtered


def build_line_protocol(symbol: str, data: dict) -> list[str]:
    """Convert options chain response to InfluxDB line protocol.

    Adapted from /home/umahar/options/query_options_continuous_rpi.py
    """
    lines = []
    timestamp_ns = int(time.time() * 1_000_000_000)

    # Underlying quote
    underlying = data.get("underlying", {})
    if underlying:
        price = underlying.get("last", underlying.get("mark", 0))
        fields = (
            f"price={price},"
            f"bid={underlying.get('bid', 0)},"
            f"ask={underlying.get('ask', 0)},"
            f"change={underlying.get('change', 0)},"
            f"percent_change={underlying.get('percentChange', 0)},"
            f"volume={underlying.get('totalVolume', 0)}i,"
            f"high={underlying.get('highPrice', 0)},"
            f"low={underlying.get('lowPrice', 0)},"
            f"open={underlying.get('openPrice', 0)}"
        )
        lines.append(f"stock_quote,symbol={symbol} {fields} {timestamp_ns}")

    # Options contracts
    for opt_type, map_key in [("CALL", "callExpDateMap"), ("PUT", "putExpDateMap")]:
        exp_map = data.get(map_key, {})
        for exp_date_str, strikes in exp_map.items():
            expiration = exp_date_str.split(":")[0]
            for strike_str, contracts in strikes.items():
                for contract in contracts:
                    strike = contract.get("strikePrice", strike_str)
                    iv = contract.get("volatility", 0)
                    itm = "true" if contract.get("inTheMoney", False) else "false"
                    fields = (
                        f"bid={contract.get('bid', 0)},"
                        f"ask={contract.get('ask', 0)},"
                        f"last={contract.get('last', 0)},"
                        f"mark={contract.get('mark', 0)},"
                        f"bid_size={contract.get('bidSize', 0)}i,"
                        f"ask_size={contract.get('askSize', 0)}i,"
                        f"volume={contract.get('totalVolume', 0)}i,"
                        f"open_interest={contract.get('openInterest', 0)}i,"
                        f"implied_volatility={iv},"
                        f"delta={contract.get('delta', 0)},"
                        f"gamma={contract.get('gamma', 0)},"
                        f"theta={contract.get('theta', 0)},"
                        f"vega={contract.get('vega', 0)},"
                        f"rho={contract.get('rho', 0)},"
                        f"in_the_money={itm},"
                        f"days_to_expiration={contract.get('daysToExpiration', 0)}i"
                    )
                    tags = (
                        f"symbol={symbol},"
                        f"option_type={opt_type},"
                        f"expiration={expiration},"
                        f"strike={strike}"
                    )
                    lines.append(f"options_data,{tags} {fields} {timestamp_ns}")

    return lines


def parse_options_for_redis(symbol: str, data: dict) -> dict:
    """Parse options chain into a JSON-serializable snapshot for Redis pub/sub."""
    underlying = data.get("underlying", {})
    quote = {
        "symbol": symbol,
        "price": underlying.get("last", underlying.get("mark", 0)),
        "bid": underlying.get("bid", 0),
        "ask": underlying.get("ask", 0),
        "change": underlying.get("change", 0),
        "percent_change": underlying.get("percentChange", 0),
        "volume": underlying.get("totalVolume", 0),
        "high": underlying.get("highPrice", 0),
        "low": underlying.get("lowPrice", 0),
        "open": underlying.get("openPrice", 0),
    }

    calls = []
    puts = []
    for opt_type, map_key, dest in [
        ("CALL", "callExpDateMap", calls),
        ("PUT", "putExpDateMap", puts),
    ]:
        exp_map = data.get(map_key, {})
        for exp_date_str, strikes in exp_map.items():
            expiration = exp_date_str.split(":")[0]
            for strike_str, contracts in strikes.items():
                for c in contracts:
                    dest.append({
                        "strike": c.get("strikePrice", float(strike_str)),
                        "expiration": expiration,
                        "bid": c.get("bid", 0),
                        "ask": c.get("ask", 0),
                        "last": c.get("last", 0),
                        "mark": c.get("mark", 0),
                        "volume": c.get("totalVolume", 0),
                        "open_interest": c.get("openInterest", 0),
                        "iv": c.get("volatility", 0),
                        "delta": c.get("delta", 0),
                        "gamma": c.get("gamma", 0),
                        "theta": c.get("theta", 0),
                        "vega": c.get("vega", 0),
                        "dte": c.get("daysToExpiration", 0),
                        "itm": c.get("inTheMoney", False),
                    })

    return {
        "symbol": symbol,
        "quote": quote,
        "calls": calls,
        "puts": puts,
        "timestamp": datetime.utcnow().isoformat(),
    }


async def ingestion_loop():
    """Main ingestion loop — polls Schwab, writes to InfluxDB, publishes to Redis.

    Polls every query_interval seconds (default 10s) and always publishes to Redis
    for live dashboard updates. Writes to InfluxDB only every 3rd cycle (~30s)
    to reduce disk I/O on the Pi.
    """
    import traceback
    influx_write_interval = 3  # write to InfluxDB every Nth cycle
    try:
        print(f"[INGESTION] Starting. Poll={settings.query_interval}s, InfluxDB write=every {settings.query_interval * influx_write_interval}s, Strikes={settings.strike_count}", flush=True)
        client = get_schwab_client()
        print("[INGESTION] Schwab client authenticated.", flush=True)
    except Exception as e:
        print(f"[INGESTION] Failed to initialize: {e}", flush=True)
        traceback.print_exc()
        return

    cycle = 0
    while True:
        try:
            symbols = await get_watchlist_symbols()
            redis = await get_redis()
            write_influx = (cycle % influx_write_interval == 0)

            for symbol in symbols:
                data = query_options_chain(client, symbol)
                if data is None:
                    continue

                underlying_price = data.get("underlying", {}).get("last", "N/A")

                # Always publish to Redis for live dashboard streaming
                snapshot = parse_options_for_redis(symbol, data)
                await redis.publish("options:updates", json.dumps(snapshot))

                # Write to InfluxDB only every Nth cycle
                if write_influx:
                    lines = build_line_protocol(symbol, data)
                    filtered_lines = filter_by_trading_hours(lines)
                    if filtered_lines:
                        success = await influx_write(filtered_lines)
                        status = "OK" if success else "FAIL"
                        print(f"[INGESTION] {symbol}: price={underlying_price}, records={len(filtered_lines)}/{len(lines)}, influx={status}", flush=True)
                    else:
                        print(f"[INGESTION] {symbol}: price={underlying_price}, records skipped (outside trading hours)", flush=True)
                else:
                    print(f"[INGESTION] {symbol}: price={underlying_price}, redis=OK", flush=True)

        except Exception as e:
            print(f"[INGESTION] Error: {e}", flush=True)
            traceback.print_exc()

        cycle += 1
        await asyncio.sleep(settings.query_interval)


@app.on_event("startup")
async def startup():
    asyncio.create_task(ingestion_loop())
