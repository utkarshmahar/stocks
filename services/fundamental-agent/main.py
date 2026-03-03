"""Fundamental AI Agent — EDGAR RAG, DCF, cash flow analysis."""
import json
from datetime import datetime

import anthropic
import httpx
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import get_settings
from shared.health import health_router
from shared.postgres import get_db, get_session_factory

app = FastAPI(title="Fundamental Agent")
app.include_router(health_router)

settings = get_settings()

ANALYSIS_PROMPT = """You are a fundamental stock analyst. Given financial data and SEC filing excerpts,
produce a structured analysis report.

Respond with ONLY valid JSON matching this schema:
{
  "valuation_summary": "string",
  "thesis": "string",
  "risks": ["string"],
  "revenue_growth": [{"year": "string", "value": number}],
  "earnings_per_share": [{"year": "string", "value": number}],
  "operating_margin": [{"year": "string", "value": number}],
  "debt_to_equity": number,
  "free_cash_flow_growth": "string",
  "moat_assessment": "string"
}
"""


def compute_dcf(fcf_values: list[float], growth_rate: float = 0.08,
                discount_rate: float = 0.10, terminal_growth: float = 0.03,
                shares_outstanding: float = 1.0) -> dict:
    """Deterministic DCF model."""
    projected = []
    last_fcf = fcf_values[-1] if fcf_values else 0
    for i in range(1, 6):
        proj = last_fcf * ((1 + growth_rate) ** i)
        projected.append(proj)

    # Terminal value
    terminal_fcf = projected[-1] * (1 + terminal_growth)
    terminal_value = terminal_fcf / (discount_rate - terminal_growth)

    # Discount to present
    pv_fcfs = sum(fcf / ((1 + discount_rate) ** (i + 1)) for i, fcf in enumerate(projected))
    pv_terminal = terminal_value / ((1 + discount_rate) ** 5)
    enterprise_value = pv_fcfs + pv_terminal
    intrinsic_per_share = enterprise_value / shares_outstanding if shares_outstanding > 0 else 0

    return {
        "projected_fcf": projected,
        "terminal_value": terminal_value,
        "pv_cash_flows": pv_fcfs,
        "pv_terminal": pv_terminal,
        "enterprise_value": enterprise_value,
        "intrinsic_value_per_share": round(intrinsic_per_share, 2),
        "assumptions": {
            "growth_rate": growth_rate,
            "discount_rate": discount_rate,
            "terminal_growth": terminal_growth,
        },
    }


async def search_filings(symbol: str, query_text: str, limit: int = 5) -> list[dict]:
    """Search pgvector for relevant filing chunks."""
    # For now, use text search until embeddings are populated
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            text("""
                SELECT chunk_text, filing_type, filing_date, metadata
                FROM filing_embeddings
                WHERE symbol = :s
                ORDER BY filing_date DESC
                LIMIT :lim
            """),
            {"s": symbol.upper(), "lim": limit},
        )
        return [
            {"text": r[0], "filing_type": r[1], "date": str(r[2]), "metadata": r[3]}
            for r in result.fetchall()
        ]


@app.post("/api/fundamental/{symbol}/analyze")
async def analyze_symbol(symbol: str, payload: dict | None = None):
    """Run full fundamental analysis."""
    symbol = symbol.upper()

    # Get filing context
    filing_context = await search_filings(symbol, "revenue earnings cash flow")

    # Get current price from API gateway
    current_price = 0.0
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"http://api-gateway:8000/api/quote/{symbol}")
            if resp.status_code == 200:
                current_price = resp.json().get("price", 0)
    except Exception:
        pass

    # Build analysis prompt
    filing_text = "\n\n".join([
        f"[{f['filing_type']} - {f['date']}]\n{f['text']}" for f in filing_context
    ]) if filing_context else "No SEC filings available yet. Provide general analysis based on your knowledge."

    user_prompt = f"""Analyze {symbol} stock fundamentally.

CURRENT PRICE: ${current_price}

SEC FILING EXCERPTS:
{filing_text}

Additional context from user: {json.dumps(payload) if payload else 'None'}

Provide your analysis as JSON."""

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=ANALYSIS_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        content = response.content[0].text.strip()
        report_data = json.loads(content)
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {e}")

    # Run DCF if we have data
    dcf_result = None
    fcf_data = payload.get("fcf_values") if payload else None
    if fcf_data:
        dcf_result = compute_dcf(
            fcf_data,
            growth_rate=payload.get("growth_rate", 0.08),
            discount_rate=payload.get("discount_rate", 0.10),
            shares_outstanding=payload.get("shares_outstanding", 1.0),
        )
        report_data["dcf"] = dcf_result

    # Save to Postgres
    factory = get_session_factory()
    async with factory() as session:
        intrinsic = dcf_result["intrinsic_value_per_share"] if dcf_result else None
        upside = ((intrinsic / current_price) - 1) * 100 if intrinsic and current_price > 0 else None
        await session.execute(
            text("""
                INSERT INTO fundamental_reports
                (symbol, report_type, report_data, ai_narrative, intrinsic_value, current_price, upside_percent)
                VALUES (:s, :rt, :rd, :ai, :iv, :cp, :up)
            """),
            {
                "s": symbol, "rt": "full_analysis",
                "rd": json.dumps(report_data),
                "ai": report_data.get("thesis", ""),
                "iv": intrinsic, "cp": current_price, "up": upside,
            },
        )
        await session.commit()

    return {
        "symbol": symbol,
        "current_price": current_price,
        "report": report_data,
        "dcf": dcf_result,
    }


@app.get("/api/fundamental/{symbol}/report")
async def get_report(symbol: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT * FROM fundamental_reports WHERE symbol = :s ORDER BY created_at DESC LIMIT 1"),
        {"s": symbol.upper()},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(404, f"No report for {symbol}")
    columns = result.keys()
    return dict(zip(columns, row))


@app.post("/api/fundamental/{symbol}/dcf")
async def run_dcf(symbol: str, payload: dict):
    """Run standalone DCF calculation."""
    fcf_values = payload.get("fcf_values", [])
    if not fcf_values:
        raise HTTPException(400, "fcf_values required")
    result = compute_dcf(
        fcf_values,
        growth_rate=payload.get("growth_rate", 0.08),
        discount_rate=payload.get("discount_rate", 0.10),
        terminal_growth=payload.get("terminal_growth", 0.03),
        shares_outstanding=payload.get("shares_outstanding", 1.0),
    )
    return {"symbol": symbol.upper(), "dcf": result}
