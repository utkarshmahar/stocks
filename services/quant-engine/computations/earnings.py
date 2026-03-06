"""Earnings date lookup via Redis cache, with Postgres fallback."""
import json
import logging
from datetime import datetime, timedelta

from shared.config import get_settings
from shared.redis_client import get_redis

logger = logging.getLogger(__name__)
settings = get_settings()

EARNINGS_CACHE_TTL = 86400  # 24 hours


async def _check_postgres_earnings(symbol: str) -> dict | None:
    """Fallback: check earnings_calendar table in Postgres."""
    try:
        from shared.postgres import get_engine
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import AsyncSession

        async with AsyncSession(get_engine()) as session:
            result = await session.execute(
                text("""
                    SELECT earnings_date FROM earnings_calendar
                    WHERE symbol = :symbol AND earnings_date >= CURRENT_DATE
                    ORDER BY earnings_date ASC LIMIT 1
                """),
                {"symbol": symbol},
            )
            row = result.fetchone()
            if row:
                return {"date": row[0].isoformat(), "source": "postgres"}
    except Exception as e:
        logger.debug("Postgres earnings lookup failed for %s: %s", symbol, e)
    return None


async def check_earnings(symbol: str) -> dict:
    """Check if earnings are nearby for a symbol.

    Uses Redis cache (24h TTL). Falls back to Postgres earnings_calendar.

    Returns dict with keys:
        earnings_nearby: bool
        earnings_date: str | None
        days_until_earnings: int | None
    """
    result = {
        "earnings_nearby": False,
        "earnings_date": None,
        "days_until_earnings": None,
    }

    redis = await get_redis()
    cache_key = f"earnings:{symbol}"

    # Check Redis cache first
    cached = await redis.get(cache_key)
    if cached:
        try:
            data = json.loads(cached)
            if data.get("date"):
                earnings_dt = datetime.strptime(data["date"], "%Y-%m-%d").date()
                days_until = (earnings_dt - datetime.utcnow().date()).days
                result["earnings_date"] = data["date"]
                result["days_until_earnings"] = days_until
                result["earnings_nearby"] = 0 <= days_until <= 14
                return result
            # Cached as "no earnings found"
            return result
        except (json.JSONDecodeError, ValueError):
            pass

    # Try Postgres fallback
    pg_result = await _check_postgres_earnings(symbol)
    if pg_result:
        await redis.setex(cache_key, EARNINGS_CACHE_TTL, json.dumps(pg_result))
        earnings_dt = datetime.strptime(pg_result["date"], "%Y-%m-%d").date()
        days_until = (earnings_dt - datetime.utcnow().date()).days
        result["earnings_date"] = pg_result["date"]
        result["days_until_earnings"] = days_until
        result["earnings_nearby"] = 0 <= days_until <= 14
        return result

    # Cache "not found" to avoid repeated lookups
    await redis.setex(cache_key, EARNINGS_CACHE_TTL, json.dumps({"date": None}))
    logger.debug("No earnings data found for %s", symbol)
    return result
