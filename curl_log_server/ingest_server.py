"""Embedded FastAPI ingest endpoint for the curl-log demo server.

Runs inside the Streamlit process on a daemon thread so a single
`streamlit run viewer_app.py` brings up both the viewer and a raw HTTP
endpoint that accepts the demo exfil POSTs.
"""
import logging
import os
import socket
import threading

import uvicorn
from fastapi import FastAPI, Request

import log_store

log = logging.getLogger("curl_log_server.ingest")

INGEST_HOST = os.getenv("CURL_LOG_INGEST_HOST", "0.0.0.0").strip() or "0.0.0.0"
INGEST_PORT = int(os.getenv("CURL_LOG_INGEST_PORT", "8000"))

app = FastAPI(title="Curl Log Ingest Server", docs_url=None, redoc_url=None)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ingest")
async def ingest(request: Request):
    """Accept an arbitrary JSON body and persist it as a captured entry."""
    try:
        payload = await request.json()
    except Exception:
        # Fall back to raw text if the body is not valid JSON.
        raw = (await request.body()).decode("utf-8", errors="replace")
        payload = {"_raw": raw}

    client_ip = request.client.host if request.client else ""
    user_agent = request.headers.get("user-agent", "")
    entry = log_store.append_entry(payload, client_ip=client_ip, user_agent=user_agent)
    log.info("[ingest] captured entry from %s", client_ip)
    return {"status": "ok", "received_at": entry["received_at"]}


# --- Background launcher --------------------------------------------------

_started = False
_start_lock = threading.Lock()


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        # connect_ex == 0 means something is already listening.
        return sock.connect_ex(("127.0.0.1" if host == "0.0.0.0" else host, port)) == 0


def start_ingest_server_in_thread(host: str = INGEST_HOST, port: int = INGEST_PORT) -> None:
    """Start uvicorn on a daemon thread. Idempotent across Streamlit re-runs.

    Streamlit re-executes the whole script on every interaction, so this guards
    against spawning duplicate servers or crashing on 'address already in use'.
    """
    global _started
    with _start_lock:
        if _started:
            return
        if _port_in_use(host, port):
            # A server (this one, from a prior script run) is already listening.
            _started = True
            return

        def _run():
            uvicorn.run(app, host=host, port=port, log_level="warning")

        thread = threading.Thread(target=_run, name="curl-log-ingest", daemon=True)
        thread.start()
        _started = True
        log.info("[ingest] started on %s:%d", host, port)


# ---------------------------------------------------------------------------
# Standalone entry point — lets systemd (or any launcher) bring up just the
# ingest server without needing a Streamlit session.
#   python3 -m ingest_server          (or python3 ingest_server.py)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import time
    start_ingest_server_in_thread()
    # Block the main thread so the daemon thread stays alive.
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
