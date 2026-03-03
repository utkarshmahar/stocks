"""Options AI Agent — LLM-powered sell options recommendations."""
import asyncio
import json
from datetime import datetime

import anthropic
import httpx
from fastapi import FastAPI, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import get_settings
from shared.health import health_router
from shared.models import Recommendation
from shared.postgres import get_db, get_session_factory

app = FastAPI(title="Options AI Agent")
app.include_router(health_router)

settings = get_settings()

SYSTEM_PROMPT = """You are an options trading AI agent specializing in high-probability income strategies.
You analyze structured quant data and recommend option selling strategies.

You MUST respond with ONLY valid JSON matching this exact schema:
{
  "symbol": "string",
  "strategy": "string (one of: Put Credit Spread, Call Credit Spread, Cash Secured Put, Covered Call, Iron Condor)",
  "legs": [{"action": "SELL|BUY", "strike": number, "type": "PUT|CALL", "expiry": "YYYY-MM-DD"}],
  "max_profit": number,
  "max_loss": number,
  "probability_estimate": number (0-1),
  "capital_required": number,
  "reasoning_summary": "string",
  "risk_flags": ["string"]
}

Rules:
- Focus on high-probability income strategies (>60% probability)
- Prefer 14-60 DTE unless data suggests otherwise
- Delta range 0.15-0.35 for short legs
- Always include risk flags for earnings, ex-div dates, high correlation
- Never recommend naked options
- Base probability on delta of short leg
"""


async def get_quant_summary(symbol: str) -> dict | None:
    """Fetch quant summary from the quant engine."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"http://quant-engine:8020/api/quant/{symbol}/summary")
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        print(f"[OPTIONS-AGENT] Quant fetch failed for {symbol}: {e}")
    return None


async def get_options_chain(symbol: str) -> dict | None:
    """Fetch current options chain from the API gateway."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"http://api-gateway:8000/api/options/{symbol}")
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        print(f"[OPTIONS-AGENT] Options chain fetch failed for {symbol}: {e}")
    return None


async def get_agent_config() -> dict:
    """Load agent config from Postgres."""
    try:
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
    except Exception:
        return {}


async def analyze_symbol(symbol: str) -> dict | None:
    """Run full analysis pipeline for a single symbol."""
    quant = await get_quant_summary(symbol)
    chain = await get_options_chain(symbol)
    if not quant:
        print(f"[OPTIONS-AGENT] No quant data for {symbol}, skipping")
        return None

    config = await get_agent_config()

    user_prompt = f"""Analyze this options data and recommend a high-probability sell strategy:

QUANT SUMMARY:
{json.dumps(quant, indent=2)}

OPTIONS CHAIN (sample - top 5 calls and puts by volume):
{json.dumps({
    "calls": sorted(chain.get("calls", []), key=lambda x: x.get("volume", 0), reverse=True)[:5] if chain else [],
    "puts": sorted(chain.get("puts", []), key=lambda x: x.get("volume", 0), reverse=True)[:5] if chain else [],
}, indent=2)}

AGENT CONFIG:
- Risk tolerance: {config.get('risk_tolerance', 'moderate')}
- DTE range: {config.get('dte_range', {"min": 14, "max": 60})}
- Delta range: {config.get('delta_range', {"min": 0.15, "max": 0.35})}
- Strategies enabled: {config.get('strategies_enabled', ['put_credit_spread', 'cash_secured_put'])}

Respond with a single JSON recommendation object. No markdown, no explanation outside JSON."""

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        content = response.content[0].text.strip()
        # Parse and validate
        rec_data = json.loads(content)
        rec = Recommendation(**rec_data)
        return rec.model_dump()
    except json.JSONDecodeError:
        print(f"[OPTIONS-AGENT] Invalid JSON from LLM for {symbol}")
        return None
    except Exception as e:
        print(f"[OPTIONS-AGENT] LLM error for {symbol}: {e}")
        return None


async def save_recommendation(rec: dict):
    """Save recommendation to Postgres."""
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            text("""
                INSERT INTO recommendations
                (symbol, strategy, legs, max_profit, max_loss, probability_estimate,
                 capital_required, reasoning_summary, risk_flags, generated_at)
                VALUES (:symbol, :strategy, :legs, :max_profit, :max_loss, :prob,
                        :capital, :reasoning, :flags, :generated_at)
            """),
            {
                "symbol": rec["symbol"],
                "strategy": rec["strategy"],
                "legs": json.dumps(rec["legs"]),
                "max_profit": rec["max_profit"],
                "max_loss": rec["max_loss"],
                "prob": rec["probability_estimate"],
                "capital": rec["capital_required"],
                "reasoning": rec["reasoning_summary"],
                "flags": json.dumps(rec["risk_flags"]),
                "generated_at": rec.get("generated_at", datetime.utcnow().isoformat()),
            },
        )
        await session.commit()
        # Audit log
        await session.execute(
            text("INSERT INTO audit_log (service, action, details) VALUES (:s, :a, :d)"),
            {"s": "options-agent", "a": "recommendation_generated", "d": json.dumps({"symbol": rec["symbol"], "strategy": rec["strategy"]})},
        )
        await session.commit()


async def risk_check(rec: dict) -> dict:
    """Call risk engine to validate recommendation."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post("http://risk-engine:8050/api/risk/validate", json=rec)
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    # Default: approve if risk engine is unavailable
    return {"approved": True, "risk_notes": "Risk engine unavailable — auto-approved", "flags": []}


@app.post("/api/agent/analyze")
async def trigger_analysis(payload: dict | None = None):
    """Manually trigger analysis for one or all symbols."""
    symbols = []
    if payload and "symbol" in payload:
        symbols = [payload["symbol"].upper()]
    else:
        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(
                text("SELECT symbol FROM watchlist WHERE active = TRUE")
            )
            symbols = [row[0] for row in result.fetchall()]

    results = []
    for symbol in symbols:
        rec = await analyze_symbol(symbol)
        if rec:
            # Risk check
            risk = await risk_check(rec)
            rec["risk_approved"] = risk["approved"]
            rec["risk_notes"] = risk["risk_notes"]
            rec["risk_flags"] = list(set(rec.get("risk_flags", []) + risk.get("flags", [])))
            await save_recommendation(rec)
            results.append(rec)

    return {"analyzed": len(symbols), "recommendations": len(results), "results": results}


async def scheduled_analysis():
    """Run analysis every 5 minutes during market hours."""
    while True:
        now = datetime.utcnow()
        # Market hours: 9:30 AM - 4:00 PM ET (14:30 - 21:00 UTC)
        hour = now.hour
        if 14 <= hour < 21:
            print("[OPTIONS-AGENT] Running scheduled analysis...")
            try:
                factory = get_session_factory()
                async with factory() as session:
                    result = await session.execute(
                        text("SELECT symbol FROM watchlist WHERE active = TRUE")
                    )
                    symbols = [row[0] for row in result.fetchall()]
                for symbol in symbols:
                    rec = await analyze_symbol(symbol)
                    if rec:
                        risk = await risk_check(rec)
                        rec["risk_approved"] = risk["approved"]
                        rec["risk_notes"] = risk["risk_notes"]
                        await save_recommendation(rec)
                        print(f"[OPTIONS-AGENT] Generated: {rec['symbol']} - {rec['strategy']}")
            except Exception as e:
                print(f"[OPTIONS-AGENT] Scheduled analysis error: {e}")
        else:
            print("[OPTIONS-AGENT] Market closed, skipping analysis.")
        await asyncio.sleep(300)  # 5 minutes


@app.on_event("startup")
async def startup():
    asyncio.create_task(scheduled_analysis())
