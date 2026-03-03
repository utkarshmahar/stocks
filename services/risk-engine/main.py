"""Risk Engine — Validates recommendations before display."""
import json
from datetime import datetime

from fastapi import FastAPI, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import get_settings
from shared.health import health_router
from shared.postgres import get_db, get_session_factory

app = FastAPI(title="Risk Engine")
app.include_router(health_router)


async def get_config() -> dict:
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(text("SELECT key, value FROM agent_config"))
        config = {}
        for row in result.fetchall():
            val = row[1]
            if isinstance(val, str):
                try:
                    val = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    pass
            config[row[0]] = val
        return config


async def get_open_positions() -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(text("SELECT symbol, market_value FROM positions"))
        return [{"symbol": r[0], "market_value": float(r[1]) if r[1] else 0} for r in result.fetchall()]


async def get_pending_recommendations(symbol: str) -> int:
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            text("SELECT COUNT(*) FROM recommendations WHERE symbol = :s AND status = 'taken'"),
            {"s": symbol},
        )
        return result.scalar() or 0


@app.post("/api/risk/validate")
async def validate_recommendation(rec: dict):
    """Validate a recommendation against risk rules."""
    flags = []
    notes = []
    config = await get_config()

    max_position_pct = float(config.get("max_position_pct", 5))
    max_loss = rec.get("max_loss", 0)
    capital_required = rec.get("capital_required", 0)

    # Check: existing exposure to this symbol
    positions = await get_open_positions()
    total_portfolio = sum(p["market_value"] for p in positions) or 100000  # default 100k
    symbol_exposure = sum(p["market_value"] for p in positions if p["symbol"] == rec.get("symbol", ""))

    current_pct = (symbol_exposure / total_portfolio) * 100 if total_portfolio > 0 else 0
    new_pct = ((symbol_exposure + capital_required) / total_portfolio) * 100 if total_portfolio > 0 else 0

    if new_pct > max_position_pct:
        flags.append(f"Position would exceed {max_position_pct}% limit ({new_pct:.1f}%)")

    # Check: DTE within configured range
    dte_range = config.get("dte_range", {"min": 14, "max": 60})
    for leg in rec.get("legs", []):
        if leg.get("expiry"):
            try:
                expiry = datetime.strptime(leg["expiry"], "%Y-%m-%d")
                dte = (expiry - datetime.utcnow()).days
                if dte < dte_range.get("min", 14):
                    flags.append(f"DTE {dte} below minimum {dte_range['min']}")
                if dte > dte_range.get("max", 60):
                    flags.append(f"DTE {dte} above maximum {dte_range['max']}")
            except ValueError:
                pass

    # Check: too many open positions on same symbol
    open_count = await get_pending_recommendations(rec.get("symbol", ""))
    if open_count >= 3:
        flags.append(f"Already {open_count} active positions on {rec.get('symbol')}")

    # Check: risk/reward ratio
    max_profit = rec.get("max_profit", 0)
    if max_loss > 0 and max_profit > 0:
        rr_ratio = max_profit / max_loss
        if rr_ratio < 0.15:
            flags.append(f"Poor risk/reward ratio: {rr_ratio:.2f}")

    # Check: probability threshold
    prob = rec.get("probability_estimate", 0)
    if prob < 0.5:
        flags.append(f"Low probability: {prob:.0%}")

    # Decision
    approved = len(flags) == 0
    risk_notes = "; ".join(flags) if flags else "All risk checks passed"

    return {"approved": approved, "risk_notes": risk_notes, "flags": flags}
