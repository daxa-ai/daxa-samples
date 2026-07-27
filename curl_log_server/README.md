# Curl Log Server

A small demo receiver for the Daxa prompt-injection exfiltration demo. It acts as
the "attacker endpoint": it accepts POSTed JSON over raw HTTP, persists each request,
and streams the captured data **live** in the browser (log-tail style) with a
**Clear Data** button.

This is the base infrastructure used to *demonstrate* (not perform) that an injected
instruction was executed by an LLM-driven app. Everything runs locally with harmless,
publicly-available data. **Local demo use only.**

## Architecture

A single `streamlit run` brings up two things in one process:

- **Streamlit viewer** (default port `8600`) — live tail of captured requests + clear button.
- **Embedded FastAPI ingest endpoint** (default port `8000`) — raw HTTP endpoint that
  Streamlit cannot expose natively. Launched on a daemon thread, guarded so Streamlit's
  script re-runs don't spawn duplicates.

Captured entries are stored as JSON Lines in `captured_logs.jsonl`.

## Files

| File | Purpose |
|------|---------|
| `viewer_app.py`   | Streamlit entry point; starts the ingest server, renders the live tail |
| `ingest_server.py`| FastAPI app (`POST /ingest`, `GET /health`) + background-thread launcher |
| `log_store.py`    | Thread-safe append / read / clear of the JSONL store |

## Run

```bash
pip install -r requirements.txt
streamlit run viewer_app.py --server.port 8600
```

- Viewer:  http://localhost:8600
- Ingest:  http://localhost:8000/ingest  (POST JSON)
- Health:  http://localhost:8000/health

## Test it

```bash
curl -X POST http://localhost:8000/ingest -H 'Content-Type: application/json' \
     -d '{"os":"macOS 15","browser":"Chrome","demo":true}'
```

The entry appears in the viewer within ~2s, newest first, showing timestamp,
source IP, and the JSON payload.

## Configuration (env vars)

| Var | Default | Meaning |
|-----|---------|---------|
| `CURL_LOG_INGEST_HOST` | `0.0.0.0` | Ingest bind host |
| `CURL_LOG_INGEST_PORT` | `8000`    | Ingest port |
| `CURL_LOG_FILE`        | `./captured_logs.jsonl` | JSONL store path |
