"""Celery Worker — Background tasks: EDGAR fetch, DCF compute, analysis."""
import json
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from celery import Celery

from shared.config import get_settings

settings = get_settings()

celery_app = Celery("worker", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    worker_max_memory_per_child=200000,  # 200MB
)

# Sync Postgres URL for celery (can't use asyncpg)
SYNC_POSTGRES_URL = settings.postgres_url.replace("postgresql+asyncpg://", "postgresql://")


def get_sync_connection():
    import psycopg2
    parts = SYNC_POSTGRES_URL.replace("postgresql://", "")
    user_pass, host_db = parts.split("@")
    user, password = user_pass.split(":")
    host_port, db = host_db.split("/")
    host, port = host_port.split(":")
    return psycopg2.connect(host=host, port=port, dbname=db, user=user, password=password)


@celery_app.task(name="fetch_edgar_filing")
def fetch_edgar_filing(symbol: str, filing_type: str = "10-K"):
    """Fetch EDGAR filing, parse, chunk, and store."""
    # Search EDGAR for company filings
    headers = {"User-Agent": "OptionsTrader research@example.com"}
    search_url = (
        f"https://efts.sec.gov/LATEST/search-index?"
        f"q=%22{symbol}%22&dateRange=custom&startdt=2023-01-01"
        f"&forms={filing_type}&hits.hits.total=5"
    )

    # Use EDGAR full-text search API
    try:
        resp = httpx.get(
            f"https://efts.sec.gov/LATEST/search-index?q={symbol}&forms={filing_type}",
            headers=headers, timeout=30.0,
        )
        if resp.status_code != 200:
            return {"status": "error", "message": f"EDGAR search failed: {resp.status_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

    # For now, use the EDGAR company search API
    try:
        cik_resp = httpx.get(
            f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={symbol}&type={filing_type}&dateb=&owner=include&count=5&search_text=&action=getcompany",
            headers=headers, timeout=30.0, follow_redirects=True,
        )
        if cik_resp.status_code == 200:
            soup = BeautifulSoup(cik_resp.text, "html.parser")
            # Extract filing links
            links = soup.find_all("a", href=re.compile(r"/Archives/edgar/data"))
            if links:
                filing_url = f"https://www.sec.gov{links[0]['href']}"
                filing_resp = httpx.get(filing_url, headers=headers, timeout=60.0, follow_redirects=True)
                if filing_resp.status_code == 200:
                    text_content = BeautifulSoup(filing_resp.text, "html.parser").get_text()
                    chunks = chunk_text(text_content, chunk_size=1000)
                    store_chunks(symbol, filing_type, chunks)
                    return {"status": "ok", "chunks": len(chunks)}
    except Exception as e:
        return {"status": "error", "message": str(e)}

    return {"status": "no_filings_found"}


def chunk_text(text: str, chunk_size: int = 1000) -> list[str]:
    """Split text into chunks for embedding."""
    # Clean whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    words = text.split()
    chunks = []
    current = []
    current_len = 0
    for word in words:
        current.append(word)
        current_len += len(word) + 1
        if current_len >= chunk_size:
            chunks.append(" ".join(current))
            current = []
            current_len = 0
    if current:
        chunks.append(" ".join(current))
    return chunks


def store_chunks(symbol: str, filing_type: str, chunks: list[str]):
    """Store filing chunks in Postgres (embeddings added later)."""
    conn = get_sync_connection()
    cur = conn.cursor()
    for i, chunk in enumerate(chunks):
        cur.execute(
            """INSERT INTO filing_embeddings (symbol, filing_type, filing_date, chunk_index, chunk_text)
               VALUES (%s, %s, %s, %s, %s)""",
            (symbol, filing_type, datetime.utcnow().date(), i, chunk),
        )
    conn.commit()
    cur.close()
    conn.close()


@celery_app.task(name="compute_dcf")
def compute_dcf_task(symbol: str, fcf_values: list[float], growth_rate: float = 0.08,
                     discount_rate: float = 0.10, shares_outstanding: float = 1.0):
    """Background DCF computation."""
    projected = []
    last_fcf = fcf_values[-1] if fcf_values else 0
    terminal_growth = 0.03
    for i in range(1, 6):
        proj = last_fcf * ((1 + growth_rate) ** i)
        projected.append(proj)

    terminal_fcf = projected[-1] * (1 + terminal_growth)
    terminal_value = terminal_fcf / (discount_rate - terminal_growth)
    pv_fcfs = sum(fcf / ((1 + discount_rate) ** (i + 1)) for i, fcf in enumerate(projected))
    pv_terminal = terminal_value / ((1 + discount_rate) ** 5)
    enterprise_value = pv_fcfs + pv_terminal
    intrinsic = enterprise_value / shares_outstanding if shares_outstanding > 0 else 0

    result = {
        "symbol": symbol,
        "intrinsic_value_per_share": round(intrinsic, 2),
        "enterprise_value": round(enterprise_value, 2),
    }

    # Store result
    conn = get_sync_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO fundamental_reports (symbol, report_type, report_data, intrinsic_value)
           VALUES (%s, %s, %s, %s)""",
        (symbol, "dcf", json.dumps(result), intrinsic),
    )
    conn.commit()
    cur.close()
    conn.close()

    return result


@celery_app.task(name="run_fundamental_analysis")
def run_fundamental_analysis(symbol: str):
    """Orchestrate full fundamental analysis."""
    # Step 1: Fetch filings
    fetch_edgar_filing.delay(symbol, "10-K")
    fetch_edgar_filing.delay(symbol, "10-Q")
    return {"status": "analysis_queued", "symbol": symbol}
