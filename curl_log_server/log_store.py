"""File-backed persistence for captured exfil POSTs.

Entries are stored one-JSON-object-per-line (JSON Lines) so they are trivially
appendable and tailable. Both the FastAPI ingest thread and the Streamlit viewer
thread touch this file, so all access is guarded by a process-wide lock.
"""
import json
import os
import threading
from datetime import datetime, timezone

_APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Path to the JSONL store; overridable via env for tests / alternate locations.
LOG_FILE = os.getenv("CURL_LOG_FILE", "").strip() or os.path.join(_APP_DIR, "captured_logs.jsonl")

_lock = threading.Lock()


def append_entry(payload: dict, client_ip: str = "", user_agent: str = "") -> dict:
    """Append one captured request as a JSON line and return the stored entry."""
    entry = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "client_ip": client_ip,
        "user_agent": user_agent,
        "payload": payload,
    }
    line = json.dumps(entry, ensure_ascii=False)
    with _lock:
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    return entry


def read_entries() -> list:
    """Return all stored entries, oldest first. Tolerant of a partial last line."""
    with _lock:
        if not os.path.exists(LOG_FILE):
            return []
        with open(LOG_FILE, "r", encoding="utf-8") as fh:
            lines = fh.readlines()

    entries = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            # Skip a half-written final line rather than failing the whole read.
            continue
    return entries


def clear() -> None:
    """Truncate the store, removing all captured entries."""
    with _lock:
        open(LOG_FILE, "w", encoding="utf-8").close()
