"""Curl Log Server — viewer.

A Streamlit app that also hosts the raw HTTP ingest endpoint (embedded FastAPI
thread). It streams captured exfil POSTs live, log-tail style, and lets you
clear the captured data.

Run:
    streamlit run viewer_app.py --server.port 8600
"""
import json
import urllib.request

import streamlit as st

import log_store
from ingest_server import INGEST_HOST, INGEST_PORT, start_ingest_server_in_thread

# Bring up the ingest endpoint (idempotent across Streamlit re-runs).
start_ingest_server_in_thread()

INGEST_DISPLAY_HOST = "localhost" if INGEST_HOST in ("0.0.0.0", "") else INGEST_HOST
INGEST_URL = f"http://{INGEST_DISPLAY_HOST}:{INGEST_PORT}/ingest"
HEALTH_URL = f"http://{INGEST_DISPLAY_HOST}:{INGEST_PORT}/health"

st.set_page_config(page_title="Curl Log Server", page_icon="📡", layout="wide")

# --- Light-mode styling & layout polish -----------------------------------
st.markdown(
    """
    <style>
      /* Keep the page comfortably centered and not too wide */
      .block-container { max-width: 1100px; padding-top: 2.5rem; padding-bottom: 3rem; }

      /* Status pill */
      .status-pill {
        display: inline-flex; align-items: center; gap: .5rem;
        height: 44px; box-sizing: border-box; padding: 0 1rem; border-radius: 999px;
        font-size: .9rem; font-weight: 600; white-space: nowrap;
      }
      .status-pill.ok   { background: #e7f6ec; color: #12794a; border: 1px solid #b6e3c6; }
      .status-pill.down { background: #fdecec; color: #b42318; border: 1px solid #f4c4c0; }
      .status-dot { width: .55rem; height: .55rem; border-radius: 50%; }
      .status-pill.ok   .status-dot { background: #12b76a; }
      .status-pill.down .status-dot { background: #f04438; }

      /* Endpoint code chip */
      .endpoint {
        display: flex; align-items: center;
        height: 44px; box-sizing: border-box;
        background: #f4f6fb; border: 1px solid #e3e8f0; border-radius: 8px;
        padding: 0 .85rem; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        font-size: .9rem; color: #1f2733; overflow-x: auto; white-space: nowrap;
      }
      .field-label {
        font-size: .78rem; font-weight: 600; color: #667085;
        text-transform: uppercase; letter-spacing: .04em; margin-bottom: .3rem;
      }

      /* Entry cards */
      .entry-meta { font-size: .82rem; color: #667085; margin: 0 0 .1rem; }
      .entry-title { font-size: .95rem; font-weight: 600; color: #1f2733; margin: 0; }

      /* Align the Clear button vertically with the inputs on its row */
      div[data-testid="stButton"] > button { width: 100%; height: 44px; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _ingest_healthy() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=1) as resp:
            return resp.status == 200
    except Exception:
        return False


# --- Header ---------------------------------------------------------------
st.title("📡 Curl Log Server")
st.caption(
    "Demo receiver — captures POSTed data live to demonstrate that an injected "
    "exfiltration instruction was executed. For local demo use only."
)

st.write("")

# --- Status / endpoint / clear (one aligned row) --------------------------
col_status, col_url, col_clear = st.columns([2, 5, 2], vertical_alignment="top", gap="large")

with col_status:
    st.markdown('<div class="field-label">Ingest server</div>', unsafe_allow_html=True)
    if _ingest_healthy():
        st.markdown(
            '<span class="status-pill ok"><span class="status-dot"></span>Healthy</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<span class="status-pill down"><span class="status-dot"></span>Down</span>',
            unsafe_allow_html=True,
        )

with col_url:
    st.markdown('<div class="field-label">Endpoint (POST JSON here)</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="endpoint">{INGEST_URL}</div>', unsafe_allow_html=True)

with col_clear:
    st.markdown('<div class="field-label">&nbsp;</div>', unsafe_allow_html=True)
    if st.button("🗑️  Clear Data", use_container_width=True):
        log_store.clear()
        st.rerun()

st.divider()


@st.fragment(run_every="2s")
def render_log_tail():
    entries = log_store.read_entries()
    st.subheader(f"Captured requests ({len(entries)})")
    if not entries:
        st.info("No requests captured yet. Waiting for incoming POSTs…")
        return
    # Newest first.
    for entry in reversed(entries):
        received = entry.get("received_at", "?")
        ip = entry.get("client_ip", "?")
        ua = entry.get("user_agent", "")
        with st.container(border=True):
            st.markdown(f'<p class="entry-title">🟢 from {ip}</p>', unsafe_allow_html=True)
            meta = received if not ua else f"{received} · {ua}"
            st.markdown(f'<p class="entry-meta">{meta}</p>', unsafe_allow_html=True)
            st.code(
                json.dumps(entry.get("payload", {}), indent=2, ensure_ascii=False),
                language="json",
            )


render_log_tail()
