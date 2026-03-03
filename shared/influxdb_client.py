import httpx
from shared.config import get_settings


async def influx_query(flux_query: str) -> list[dict]:
    """Execute a Flux query against InfluxDB and return parsed results."""
    settings = get_settings()
    url = f"{settings.influxdb_url}/api/v2/query?org={settings.influxdb_org}"
    headers = {
        "Authorization": f"Token {settings.influxdb_token}",
        "Content-Type": "application/vnd.flux",
        "Accept": "application/csv",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, content=flux_query, headers=headers)
        resp.raise_for_status()
        return _parse_csv(resp.text)


def _parse_csv(csv_text: str) -> list[dict]:
    """Parse InfluxDB CSV response into list of dicts."""
    results = []
    lines = csv_text.strip().split("\n")
    if len(lines) < 2:
        return results
    headers = None
    for line in lines:
        if line.startswith("#") or line.strip() == "":
            continue
        cols = line.split(",")
        if headers is None:
            headers = cols
            continue
        row = {}
        for i, h in enumerate(headers):
            if i < len(cols) and h.strip() and h.strip() not in ("", "result", "table"):
                row[h.strip()] = cols[i].strip()
        if row:
            results.append(row)
    return results


async def influx_write(lines: list[str]) -> bool:
    """Write line protocol data to InfluxDB in batch."""
    settings = get_settings()
    url = (
        f"{settings.influxdb_url}/api/v2/write"
        f"?org={settings.influxdb_org}&bucket={settings.influxdb_bucket}&precision=ns"
    )
    headers = {
        "Authorization": f"Token {settings.influxdb_token}",
        "Content-Type": "text/plain",
    }
    payload = "\n".join(lines)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, content=payload, headers=headers)
        return resp.status_code == 204
