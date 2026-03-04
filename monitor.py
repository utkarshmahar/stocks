#!/usr/bin/env python3
"""Lightweight Stack Monitor Dashboard for Options Trading Platform.

Runs natively on the Pi (not in Docker). Zero external dependencies.
Access at http://localhost:8888
"""

import json
import os
import subprocess
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = 8888
TOKEN_PATH = "/home/umahar/stocks/schwab_token.json"
TOKEN_LIFETIME_DAYS = 7

SERVICES = [
    ("API Gateway",    "http://localhost:8000/health"),
    ("Ingestion",      "http://localhost:8010/health"),
    ("Quant Engine",   "http://localhost:8020/health"),
    ("Options Agent",  "http://localhost:8030/health"),
    ("Portfolio",      "http://localhost:8040/health"),
    ("Risk Engine",    "http://localhost:8050/health"),
    ("Fundamental",    "http://localhost:8060/health"),
]

INFLUXDB_HEALTH = "http://localhost:8086/health"


def get_schwab_token_info():
    """Read schwab_token.json and compute expiry info."""
    try:
        with open(TOKEN_PATH, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return {"status": "error", "message": str(e)}

    created = data.get("creation_timestamp")
    if created is None:
        # Try mtime as fallback
        mtime = os.path.getmtime(TOKEN_PATH)
        created = mtime
    created_dt = datetime.fromtimestamp(float(created), tz=timezone.utc)
    expires_dt = created_dt + timedelta(days=TOKEN_LIFETIME_DAYS)
    now = datetime.now(tz=timezone.utc)
    remaining = expires_dt - now
    total_seconds = remaining.total_seconds()

    if total_seconds <= 0:
        color, label = "red", "EXPIRED"
    elif total_seconds < 86400:  # < 1 day
        hours = int(total_seconds // 3600)
        color, label = "red", f"{hours}h remaining"
    elif total_seconds < 2 * 86400:  # < 2 days
        hours = int(total_seconds // 3600)
        color, label = "orange", f"1d {hours % 24}h remaining"
    else:
        days = int(total_seconds // 86400)
        hours = int((total_seconds % 86400) // 3600)
        color, label = "lime", f"{days}d {hours}h remaining"

    return {
        "status": "ok",
        "color": color,
        "label": label,
        "created": created_dt.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "expires": expires_dt.strftime("%Y-%m-%d %H:%M:%S UTC"),
    }


def get_docker_containers():
    """List all project containers with status."""
    try:
        result = subprocess.run(
            ["sudo", "docker", "ps", "-a",
             "--filter", "label=com.docker.compose.project",
             "--format", "{{.Names}}\t{{.Status}}\t{{.State}}"],
            capture_output=True, text=True, timeout=10,
        )
        containers = []
        for line in result.stdout.strip().splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            name = parts[0] if len(parts) > 0 else "unknown"
            status = parts[1] if len(parts) > 1 else "unknown"
            state = parts[2] if len(parts) > 2 else "unknown"
            containers.append({"name": name, "status": status, "state": state})
        containers.sort(key=lambda c: c["name"])
        return containers
    except Exception as e:
        return [{"name": "error", "status": str(e), "state": "error"}]


def check_health(url, timeout=3):
    """Ping a /health endpoint, return (status_code, latency_ms) or None."""
    try:
        start = time.monotonic()
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ms = int((time.monotonic() - start) * 1000)
            return resp.status, ms
    except urllib.error.HTTPError as e:
        return e.code, 0
    except Exception:
        return None, 0


def build_html():
    """Build the full dashboard HTML."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Token info
    token = get_schwab_token_info()
    if token["status"] == "ok":
        token_html = (
            f'<span style="color:{token["color"]}">&#9679;</span> '
            f'<b>{token["label"]}</b><br>'
            f'Created: {token["created"]}<br>'
            f'Expires: {token["expires"]}<br>'
            f'<span style="color:#888">File: {TOKEN_PATH}</span>'
        )
    else:
        token_html = f'<span style="color:red">&#9679;</span> {token["message"]}'

    # Docker containers
    containers = get_docker_containers()
    cont_rows = []
    for c in containers:
        if c["state"] == "running":
            dot = '<span style="color:lime">&#9679;</span>'
        elif c["state"] == "error":
            dot = '<span style="color:red">&#9679;</span>'
        else:
            dot = '<span style="color:gray">&#9675;</span>'
        cont_rows.append(f'{dot} {c["name"]:30s} {c["status"]}')
    containers_html = "<br>".join(cont_rows) if cont_rows else "No containers found"

    # Service health
    svc_rows = []
    for name, url in SERVICES:
        code, ms = check_health(url)
        if code and 200 <= code < 300:
            dot = '<span style="color:lime">&#9679;</span>'
            info = f"{code} OK &nbsp; {ms}ms"
        elif code:
            dot = '<span style="color:orange">&#9679;</span>'
            info = f"{code}"
        else:
            dot = '<span style="color:red">&#9679;</span>'
            info = "unreachable"
        path = url.replace("http://localhost", "")
        svc_rows.append(f'{dot} {name:20s} {path:25s} {info}')
    services_html = "<br>".join(svc_rows)

    # InfluxDB
    influx_code, influx_ms = check_health(INFLUXDB_HEALTH)
    if influx_code and 200 <= influx_code < 300:
        influx_html = f'<span style="color:lime">&#9679;</span> {INFLUXDB_HEALTH} &nbsp; {influx_code} OK &nbsp; {influx_ms}ms'
    else:
        influx_html = f'<span style="color:red">&#9679;</span> {INFLUXDB_HEALTH} &nbsp; unreachable'

    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="30">
<title>Stack Monitor</title>
<style>
  body {{ background:#1a1a2e; color:#e0e0e0; font-family:'Courier New',monospace;
         margin:0; padding:20px; font-size:14px; }}
  .box {{ background:#16213e; border:1px solid #0f3460; border-radius:8px;
          padding:16px; margin-bottom:14px; }}
  .box h2 {{ margin:0 0 10px 0; font-size:15px; color:#e94560;
             border-bottom:1px solid #0f3460; padding-bottom:6px; }}
  h1 {{ color:#e94560; margin:0 0 4px 0; font-size:20px; }}
  .ts {{ color:#888; margin-bottom:16px; font-size:13px; }}
  pre {{ margin:0; white-space:pre-wrap; line-height:1.7; }}
</style>
</head><body>
<h1>Options Trading Platform &mdash; Stack Monitor</h1>
<div class="ts">Last checked: {now} &nbsp; | &nbsp; Auto-refresh: 30s</div>

<div class="box">
  <h2>SCHWAB TOKEN</h2>
  <pre>{token_html}</pre>
</div>

<div class="box">
  <h2>DOCKER CONTAINERS</h2>
  <pre>{containers_html}</pre>
</div>

<div class="box">
  <h2>SERVICE HEALTH (HTTP endpoints)</h2>
  <pre>{services_html}</pre>
</div>

<div class="box">
  <h2>INFLUXDB (native)</h2>
  <pre>{influx_html}</pre>
</div>

</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        html = build_html()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, fmt, *args):
        # Quiet logging — only errors
        pass


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Stack Monitor running on http://0.0.0.0:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()
