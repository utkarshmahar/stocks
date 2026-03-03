"""Portfolio Service — Real-time P&L with premium-adjusted cost basis."""
import asyncio
import json
from datetime import datetime

from fastapi import FastAPI, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import get_settings
from shared.health import health_router
from shared.schwab_auth import get_schwab_client
from shared.postgres import get_db, get_session_factory
from shared.redis_client import get_redis

app = FastAPI(title="Portfolio Service")
app.include_router(health_router)

settings = get_settings()


def fetch_schwab_positions(client) -> list[dict]:
    """Fetch positions from Schwab API."""
    try:
        # First get account numbers/hashes
        acct_resp = client.get_account_numbers()
        if acct_resp.status_code != 200:
            print(f"[PORTFOLIO] Schwab account numbers API returned {acct_resp.status_code} (may need trading permissions)", flush=True)
            return []
        accounts = acct_resp.json()
        if not accounts:
            print("[PORTFOLIO] No accounts found", flush=True)
            return []

        # Get positions for first account
        hash_val = accounts[0].get("hashValue", "")
        response = client.get_account(hash_val, fields=[client.Account.Fields.POSITIONS])
        if response.status_code != 200:
            print(f"[PORTFOLIO] Schwab positions API returned {response.status_code}", flush=True)
            return []
        data = response.json()
        positions = []
        for account in data if isinstance(data, list) else [data]:
            acct_data = account.get("securitiesAccount", account)
            for pos in acct_data.get("positions", []):
                instrument = pos.get("instrument", {})
                positions.append({
                    "symbol": instrument.get("symbol", ""),
                    "quantity": pos.get("longQuantity", 0) - pos.get("shortQuantity", 0),
                    "avg_price": pos.get("averagePrice", 0),
                    "current_price": pos.get("marketValue", 0) / max(pos.get("longQuantity", 1), 1),
                    "market_value": pos.get("marketValue", 0),
                    "asset_type": instrument.get("assetType", "EQUITY"),
                })
        return positions
    except Exception as e:
        print(f"[PORTFOLIO] Error fetching positions: {e}")
        return []


async def sync_positions():
    """Sync positions from Schwab to Postgres."""
    client = get_schwab_client()
    positions = fetch_schwab_positions(client)
    if not positions:
        return

    factory = get_session_factory()
    async with factory() as session:
        for pos in positions:
            cost_basis = pos["quantity"] * pos["avg_price"]
            pnl = pos["market_value"] - cost_basis
            pnl_pct = (pnl / cost_basis * 100) if cost_basis > 0 else 0

            await session.execute(
                text("""
                    INSERT INTO positions (symbol, quantity, avg_price, current_price,
                        market_value, cost_basis, pnl, pnl_percent, asset_type, last_synced)
                    VALUES (:symbol, :qty, :avg, :cur, :mv, :cb, :pnl, :pnl_pct, :at, NOW())
                    ON CONFLICT (symbol, asset_type)
                    DO UPDATE SET quantity = :qty, avg_price = :avg, current_price = :cur,
                        market_value = :mv, cost_basis = :cb, pnl = :pnl,
                        pnl_percent = :pnl_pct, last_synced = NOW()
                """),
                {
                    "symbol": pos["symbol"], "qty": pos["quantity"],
                    "avg": pos["avg_price"], "cur": pos["current_price"],
                    "mv": pos["market_value"], "cb": cost_basis,
                    "pnl": pnl, "pnl_pct": pnl_pct, "at": pos["asset_type"],
                },
            )
        await session.commit()

    # Publish update to Redis
    redis = await get_redis()
    await redis.publish("portfolio:updates", json.dumps({
        "event": "positions_synced",
        "count": len(positions),
        "timestamp": datetime.utcnow().isoformat(),
    }))
    print(f"[PORTFOLIO] Synced {len(positions)} positions")


@app.post("/api/portfolio/sync")
async def trigger_sync():
    await sync_positions()
    return {"status": "synced"}


@app.get("/api/portfolio/adjusted")
async def get_adjusted_positions(db: AsyncSession = Depends(get_db)):
    """Get positions with premium-adjusted cost basis."""
    result = await db.execute(text("""
        SELECT p.symbol, p.quantity, p.avg_price, p.current_price, p.market_value,
            p.cost_basis, p.pnl, p.pnl_percent, p.asset_type, p.last_synced,
            COALESCE(SUM(pc.premium_collected * pc.contracts * 100), 0) as total_premium
        FROM positions p
        LEFT JOIN premium_collections pc ON p.symbol = pc.underlying_symbol AND pc.status != 'cancelled'
        GROUP BY p.id
        ORDER BY p.symbol
    """))
    rows = result.fetchall()
    positions = []
    for r in rows:
        total_premium = float(r[10])
        cost_basis = float(r[5]) if r[5] else 0
        adjusted_cost = cost_basis - total_premium
        qty = float(r[1])
        effective_per_share = adjusted_cost / qty if qty > 0 else 0
        adjusted_pnl = float(r[4] or 0) - adjusted_cost

        positions.append({
            "symbol": r[0], "quantity": qty, "avg_price": float(r[2]),
            "current_price": float(r[3]) if r[3] else None,
            "market_value": float(r[4]) if r[4] else None,
            "original_cost_basis": cost_basis,
            "total_premium_collected": total_premium,
            "adjusted_cost_basis": adjusted_cost,
            "effective_cost_per_share": effective_per_share,
            "adjusted_pnl": adjusted_pnl,
            "asset_type": r[8],
            "last_synced": r[9].isoformat() if r[9] else None,
        })
    return positions


@app.post("/api/portfolio/premium")
async def record_premium(payload: dict, db: AsyncSession = Depends(get_db)):
    """Record a premium collection from a sold option."""
    await db.execute(
        text("""
            INSERT INTO premium_collections
            (underlying_symbol, option_symbol, strategy, premium_collected, contracts, open_date, notes)
            VALUES (:sym, :opt, :strat, :prem, :contracts, :date, :notes)
        """),
        {
            "sym": payload["underlying_symbol"].upper(),
            "opt": payload.get("option_symbol"),
            "strat": payload.get("strategy"),
            "prem": payload["premium_collected"],
            "contracts": payload.get("contracts", 1),
            "date": payload.get("open_date", datetime.utcnow().isoformat()),
            "notes": payload.get("notes"),
        },
    )
    await db.commit()
    return {"status": "recorded"}


async def sync_loop():
    """Sync positions every 5 minutes."""
    while True:
        try:
            await sync_positions()
        except Exception as e:
            print(f"[PORTFOLIO] Sync error: {e}")
        await asyncio.sleep(300)


@app.on_event("startup")
async def startup():
    asyncio.create_task(sync_loop())
