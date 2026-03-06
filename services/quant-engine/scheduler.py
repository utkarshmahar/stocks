"""Scheduler: 5-min compute loop for quant summaries.

Runs during market hours (9:30 AM - 4:00 PM ET, Mon-Fri).
Computes IV analysis, flow analysis, market regime, earnings, and strategy screens
for each watchlist symbol. Stores results in Redis (instant reads) and InfluxDB (charting).
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timezone, timedelta

from shared.config import get_settings
from shared.redis_client import get_redis
from shared.influxdb_client import influx_write, influx_query
from shared.models import QuantSummaryV2, EarningsInfo

from computations import (
    compute_iv_analysis,
    compute_flow_analysis,
    compute_market_regime,
    check_earnings,
    scan_strikes,
)
from strategies import STRATEGIES

logger = logging.getLogger(__name__)
settings = get_settings()

COMPUTE_INTERVAL = 300  # 5 minutes
REDIS_TTL = 600  # 10 minutes
ET = timezone(timedelta(hours=-5))  # Eastern Time (simplified, no DST handling)


def is_market_hours() -> bool:
    """Check if US market is open (approx: Mon-Fri, 9:30-16:00 ET)."""
    now_et = datetime.now(ET)
    if now_et.weekday() >= 5:  # Saturday, Sunday
        return False
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now_et <= market_close


async def get_watchlist_symbols() -> list[str]:
    """Get active symbols from Redis watchlist cache, fallback to config defaults."""
    redis = await get_redis()
    cached = await redis.get("watchlist:symbols")
    if cached:
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            pass

    # Fallback: query Postgres via InfluxDB-stored symbols or config
    # For simplicity, use config defaults and let the API gateway cache the watchlist
    symbols = settings.symbols_list
    logger.info("Using default symbols: %s", symbols)
    return symbols


async def _get_current_price(symbol: str) -> float:
    """Get current underlying price from InfluxDB."""
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


async def compute_symbol(symbol: str) -> QuantSummaryV2 | None:
    """Run all computations for a single symbol."""
    price = await _get_current_price(symbol)
    if price == 0:
        logger.warning("No price data for %s, skipping", symbol)
        return None

    # Run independent computations in parallel
    iv_result, flow_result, regime_result, earnings_result = await asyncio.gather(
        compute_iv_analysis(symbol),
        compute_flow_analysis(symbol),
        compute_market_regime(symbol, price),
        check_earnings(symbol),
    )

    # Build partial summary for strategy pre-filters
    partial_summary = {
        "iv_percentile": iv_result.get("iv_percentile"),
        "iv_rank": iv_result.get("iv_rank"),
        "earnings": earnings_result,
    }

    # Scan strikes for strategy screening
    chain = await scan_strikes(symbol)

    # Run strategies sequentially (they depend on chain data)
    strategy_screens = []
    for strategy in STRATEGIES:
        if not strategy.passes_filter(partial_summary):
            logger.debug("Strategy %s filtered out for %s", strategy.slug, symbol)
            continue
        try:
            screen = await strategy.screen(
                symbol, price, chain["calls"], chain["puts"], partial_summary,
            )
            if screen.candidates:
                strategy_screens.append(screen)
        except Exception as e:
            logger.error("Strategy %s failed for %s: %s", strategy.slug, symbol, e)

    return QuantSummaryV2(
        symbol=symbol,
        current_price=price,
        # IV
        iv_percentile=iv_result.get("iv_percentile"),
        iv_rank=iv_result.get("iv_rank"),
        current_iv=iv_result.get("current_iv"),
        iv_trend=iv_result.get("iv_trend"),
        # Flow
        put_call_skew=flow_result.get("put_call_skew"),
        volume_oi_ratio=flow_result.get("volume_oi_ratio"),
        unusual_activity=flow_result.get("unusual_activity", False),
        total_call_volume=flow_result.get("total_call_volume", 0),
        total_put_volume=flow_result.get("total_put_volume", 0),
        total_call_oi=flow_result.get("total_call_oi", 0),
        total_put_oi=flow_result.get("total_put_oi", 0),
        # Market regime
        vix_level=regime_result.get("vix_level"),
        expected_weekly_move=regime_result.get("expected_weekly_move"),
        expected_move_pct=regime_result.get("expected_move_pct"),
        # Earnings
        earnings=EarningsInfo(**earnings_result),
        # Strategies
        strategy_screens=strategy_screens,
        # Meta
        source="scheduler",
    )


async def store_to_redis(summary: QuantSummaryV2) -> None:
    """Store summary in Redis with TTL."""
    redis = await get_redis()
    key = f"quant:{summary.symbol}"
    data = summary.model_dump_json()
    await redis.setex(key, REDIS_TTL, data)
    logger.debug("Stored %s in Redis (%d bytes)", key, len(data))


async def store_to_influxdb(summary: QuantSummaryV2) -> None:
    """Write summary stats to InfluxDB for time-series charting."""
    ts = int(time.time() * 1_000_000_000)  # nanoseconds
    lines = []

    fields = []
    if summary.iv_percentile is not None:
        fields.append(f"iv_percentile={summary.iv_percentile}")
    if summary.iv_rank is not None:
        fields.append(f"iv_rank={summary.iv_rank}")
    if summary.current_iv is not None:
        fields.append(f"current_iv={summary.current_iv}")
    if summary.iv_trend is not None:
        fields.append(f"iv_trend={summary.iv_trend}")
    if summary.put_call_skew is not None:
        fields.append(f"put_call_skew={summary.put_call_skew}")
    if summary.volume_oi_ratio is not None:
        fields.append(f"volume_oi_ratio={summary.volume_oi_ratio}")
    if summary.vix_level is not None:
        fields.append(f"vix_level={summary.vix_level}")
    if summary.expected_weekly_move is not None:
        fields.append(f"expected_weekly_move={summary.expected_weekly_move}")
    fields.append(f"current_price={summary.current_price}")
    fields.append(f"unusual_activity={'true' if summary.unusual_activity else 'false'}")

    if fields:
        field_str = ",".join(fields)
        lines.append(f"quant_summary,symbol={summary.symbol} {field_str} {ts}")

    if lines:
        ok = await influx_write(lines)
        if not ok:
            logger.warning("Failed to write quant_summary to InfluxDB for %s", summary.symbol)


async def run_compute_cycle() -> int:
    """Run one full compute cycle for all watchlist symbols. Returns count of computed."""
    symbols = await get_watchlist_symbols()
    if not symbols:
        logger.info("No symbols in watchlist, skipping cycle")
        return 0

    logger.info("Starting compute cycle for %d symbols: %s", len(symbols), symbols)
    computed = 0

    # Compute symbols in parallel (bounded to avoid overwhelming Pi)
    sem = asyncio.Semaphore(3)

    async def compute_with_sem(sym: str):
        async with sem:
            return await compute_symbol(sym)

    results = await asyncio.gather(
        *[compute_with_sem(s) for s in symbols],
        return_exceptions=True,
    )

    for sym, result in zip(symbols, results):
        if isinstance(result, Exception):
            logger.error("Compute failed for %s: %s", sym, result)
            continue
        if result is None:
            continue

        # Store to Redis + InfluxDB in parallel
        await asyncio.gather(
            store_to_redis(result),
            store_to_influxdb(result),
        )
        computed += 1

    logger.info("Compute cycle complete: %d/%d symbols", computed, len(symbols))
    return computed


async def scheduler_loop():
    """Main scheduler loop. Runs compute every 5 minutes during market hours."""
    logger.info("Quant scheduler started (interval=%ds)", COMPUTE_INTERVAL)

    # Run once immediately on startup
    try:
        await run_compute_cycle()
    except Exception as e:
        logger.error("Initial compute cycle failed: %s", e)

    while True:
        await asyncio.sleep(COMPUTE_INTERVAL)
        if not is_market_hours():
            logger.debug("Market closed, skipping compute cycle")
            continue
        try:
            await run_compute_cycle()
        except Exception as e:
            logger.error("Compute cycle error: %s", e)
