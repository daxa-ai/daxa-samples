# Deck Builder App

A Streamlit app that turns a file upload (spreadsheet or Word document) plus
a text instruction into an LLM-generated slide-by-slide outline. Two modes,
selectable from the sidebar:

| Mode | LLM routing | Pebblo headers |
|------|-------------|-----------------|
| **Safe Infer** | Daxa/Proxima SafeInfer gateway | ✅ |
| **Insecure Inference** | Direct to the configured model (`OPENAI_API_KEY`) | ❌ |

---

## Project Structure

```
deck_builder_app/
├── deck_builder.py            # Main app — both modes (port 8501)
├── utils.py                   # Shared config, API helpers, UI helpers
├── file_parser.py              # Standalone .xlsx/.xlsm/.docx -> text parser (no Streamlit dependency)
├── prompts.yaml                 # Sample deck-building prompts, by language
├── static/                       # Reference docs shown in the sidebar "Documents" section
│   └── source_files/               # Files iterated by the multi-file pipeline (see below)
├── requirements.txt
├── .env                          # Environment variables (create from .env.example)
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

# ── Deck source files (folder-iteration pipeline, both modes) ────────────────
DECK_SOURCE_DIR=static/source_files
ENABLE_MULTI_PASS=false   # true = slower, per-file resilient pipeline (see below)

# ── Debug ─────────────────────────────────────────────────────────────────────
DEBUG=false   # true = append a "⏱ Timing" breakdown to every response
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
4. Optionally upload a `.xlsx`/`.xlsm`/`.docx` file under **📎 Upload a file
   (optional)**.
5. Type your instructions and click **🚀 Generate Outline**.
6. The response streams in, with the model (and, in Safe Infer, the
   requesting user) shown underneath, followed by a `⏱ Timing` line breaking
   down where the time went.

Sidebar also has: API Status (Safe Infer), Prompt Language, Sample Prompts,
Documents (Safe Infer: reference docs + source files, both clickable;
Insecure Inference: source files only), and Statistics.

### Single upload vs. the source-files folder

Every Send does one of two things, depending on whether a file is uploaded
that turn:

- **File uploaded** — only that file is used (single call, same as before).
  `DECK_SOURCE_DIR` is not touched this turn.
- **No file uploaded** — every `.xlsx`/`.xlsm`/`.docx` in `DECK_SOURCE_DIR`
  (`static/source_files/` by default) is used, per `ENABLE_MULTI_PASS`:
  - **`false` (default) — single pass:** all eligible files' content is
    combined into one prompt and sent as a single call. Fastest option — one
    LLM round-trip regardless of file count — but if that one call errors or
    gets blocked, the whole turn fails (a file that fails to *parse* is still
    skipped gracefully, since that's a local check with no LLM call involved).
  - **`true` — multi pass:** one non-streaming call per file collects a short
    set of key points from that file alone, then a final call combines
    whatever came back into one outline. If a file's call fails — in
    particular an HTTP 403, meaning Safe Infer blocked that file's content —
    that file is skipped and the rest of the run continues. Slower (N+1
    calls instead of 1), but a blocked/failed file never prevents the rest
    of the deck from being generated.
  - If the folder is empty, the instructions are sent on their own either way.

Both modes of the folder-iteration pipeline run identically in Insecure
Inference — only the client differs (direct to the configured model vs.
through the Daxa gateway).

In Safe Infer, `DOC_ACCESS_ALLOWED` group-gating applies to `DECK_SOURCE_DIR`
too: a file the current user's groups can't access is excluded from
processing, not just hidden from the sidebar list.

### Timing

Set `DEBUG=true` to append a deterministic `⏱ Timing` line (computed by the
app, not the LLM) to every response, so it's clear which step is the
bottleneck. Off by default — end users don't need to see it, and skip/lock
notes (which files were excluded and why) are always shown regardless of
this setting:

- Single file / no file / single-pass folder iteration:
  `parse <Xs>; LLM call <Ys> (first token <Zs>); total <Ts>`.
- Multi-pass folder iteration (`ENABLE_MULTI_PASS=true`):
  `parse <Xs>; map calls <Ys> (file1 <a>s, file2 <b>s, ...);
  reduce call <Zs> (first token <Ws>); total <Ts>`.

In multi-pass mode the per-file map calls run one at a time, so that total
scales with the number of eligible source files — reducing the file count,
using a faster model, trimming very large files (see `MAX_ROWS_PER_SHEET` /
`MAX_CHARS` in `file_parser.py`), or switching to single pass are the main
levers if that step dominates.

### Topic-based file routing

Set `FILE_TOPIC_HINTS` (filename -> topic description, same style as
`DOC_ACCESS_ALLOWED`) to have the app skip reading/sending files that clearly
don't match the question — before any file is parsed or sent to the LLM, not
as a prompt instruction hoping the model ignores irrelevant content:

- The user's prompt is checked for keyword overlap with each hinted file's
  topic description.
- A hinted file whose topic doesn't overlap the prompt is excluded from that
  turn entirely (skipped, cheaper and faster than including it).
- Files with no hint configured are always included.
- If no hinted file matches at all, nothing is excluded — an unexpectedly
  worded question never silently loses a file it might have needed.
- Any exclusion is noted in the response, e.g. *"1 file(s) excluded as not
  relevant to this question: Board Meeting Summary Doc.docx."*

---

## Notes

- `.xlsx`/`.xlsm`/`.docx` files are parsed into text today; other file types
  are accepted by the uploader but sent as instructions-only (with a
  warning). Unsupported files placed in `DECK_SOURCE_DIR` are silently
  ignored by the folder-iteration pipeline.
- `file_parser.py` has no Streamlit dependency — it can be reused as-is in
  other apps or scripts that need file-to-text conversion.

**Powered by Daxa Proxima · SafeInfer · OpenAI**
