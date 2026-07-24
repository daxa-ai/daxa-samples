# Deck Builder App

A Streamlit app that turns a spreadsheet upload plus a text instruction into
an LLM-generated slide-by-slide outline. Two modes, selectable from the
sidebar:

| Mode | LLM routing | Pebblo headers |
|------|-------------|-----------------|
| **Safe Infer** | Daxa/Proxima SafeInfer gateway | ✅ |
| **Insecure Inference** | Direct to the configured model (`OPENAI_API_KEY`) | ❌ |

---

## Project Structure

```
deck_builder_app/
├── deck_builder.py   # Main app — both modes (port 8501)
├── utils.py          # Shared config, API helpers, UI helpers
├── file_parser.py     # Standalone .xlsx -> text parser (no Streamlit dependency)
├── prompts.yaml        # Sample deck-building prompts, by language
├── static/              # Reference docs shown in the sidebar "Documents" section
├── requirements.txt
├── .env                 # Environment variables (create from .env.example)
└── README.md
```

---

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

```env
# ── SafeInfer / Proxima gateway (Safe Infer mode) ────────────────────────────
PROXIMA_HOST=https://<your-proxima-host>/
PEBBLO_API_KEY=pebblo_<your-global-key>

# ── User identity (forwarded to Proxima as X-PEBBLO-USER / X-PEBBLO-USER-GROUPS) ──
PEBBLO_USERS=alice@daxaai.onmicrosoft.com, bob@daxaai.onmicrosoft.com
PEBBLO_USER_GROUPS_MAP=alice@daxaai.onmicrosoft.com:executives@daxaai.onmicrosoft.com; bob@daxaai.onmicrosoft.com:customer-support@daxaai.onmicrosoft.com
USER_EMAIL=you@example.com
USER_TEAM=YourTeam

# ── Model (Safe Infer dropdown default / Insecure Inference default) ────────
MODEL=gpt-4o-mini

# ── Insecure Inference mode (direct to model, no gateway) ────────────────────
OPENAI_API_KEY=sk-proj-...

# ── Documents section (sidebar reference links, Safe Infer only) ────────────
DOCS_DIR=static
DOC_ACCESS_ALLOWED={}
```

Run it:

```bash
streamlit run deck_builder.py
```

Open `http://localhost:8501`.

---

## Using the app

1. Pick a mode: **Safe Infer** or **Insecure Inference**.
2. (Safe Infer only) pick a user (Alice/Bob) — this is forwarded to Proxima
   as `X-PEBBLO-USER` / `X-PEBBLO-USER-GROUPS`.
3. Pick or refresh a model.
4. Optionally upload a `.xlsx` file next to the instructions box.
5. Type your instructions and click **🚀 Generate Outline**.
6. The response streams in, with the model (and, in Safe Infer, the
   requesting user) shown underneath.

Sidebar also has: API Status (Safe Infer), Prompt Language, Sample Prompts,
Documents (Safe Infer), and Statistics.

---

## Notes

- Only `.xlsx`/`.xlsm` files are parsed into spreadsheet content today; other
  file types are accepted by the uploader but sent as instructions-only (with
  a warning).
- `file_parser.py` has no Streamlit dependency — it can be reused as-is in
  other apps or scripts that need spreadsheet-to-text conversion.

**Powered by Daxa Proxima · SafeInfer · OpenAI**
