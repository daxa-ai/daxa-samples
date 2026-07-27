"""Deck Builder App — upload a file (or use a folder of them) + instructions, get a slide outline back.

Two modes, selectable from the sidebar:
  - Safe Infer:         routed through the Daxa/Proxima SafeInfer gateway (Pebblo headers).
  - Insecure Inference:  calls the configured model directly, no gateway, no Pebblo headers.
"""
import ast
import os
import time

import streamlit as st
from openai import APIStatusError, OpenAI

from file_parser import FileParsingError, is_supported_file, parse_file_to_text
from utils import (
    API_BASE_URL,
    API_KEY,
    CUSTOM_CSS,
    FOOTER_HTML,
    MAIN_HEADER_HTML,
    MODEL,
    PEBBLO_USER_GROUPS_MAP,
    PEBBLO_USERS_LIST,
    X_PEBBLO_USER,
    X_PEBBLO_USER_GROUPS,
    display_chat_message,
    format_display_name,
    get_available_models,
    get_direct_llm_client,
    get_llm_client,
    get_welcome_html,
    load_prompts_from_yaml,
    merge_env_model_into_model_list,
    test_api_connection,
)

# ---------------------------------------------------------------------------
# Documents section config
#
# DOCS_DIR: human-browsable reference links (Safe Infer sidebar only), never
#           sent to the LLM.
# DECK_SOURCE_DIR: the "predefined local location" iterated by the multi-file
#           map-reduce pipeline (see below) whenever no file is uploaded
#           directly. Listed in the sidebar in both modes, alongside DOCS_DIR
#           in Safe Infer.
# ---------------------------------------------------------------------------

_APP_DIR = os.path.dirname(__file__)
_STATIC_ROOT = os.path.join(_APP_DIR, "static")

_raw_docs_dir = os.getenv("DOCS_DIR", "").strip() or "static"
DOCS_DIR = _raw_docs_dir if os.path.isabs(_raw_docs_dir) else os.path.join(_APP_DIR, _raw_docs_dir)

# Nested under static/ by default so Streamlit's static file serving can make
# these clickable too (enableStaticServing only serves the app's static/ folder).
_raw_source_dir = os.getenv("DECK_SOURCE_DIR", "").strip() or "static/source_files"
DECK_SOURCE_DIR = _raw_source_dir if os.path.isabs(_raw_source_dir) else os.path.join(_APP_DIR, _raw_source_dir)

# Folder-iteration pipeline mode. Default (false): single pass — every eligible
# file's content is combined into ONE prompt and sent in a single LLM call
# (fast, but a block/error on that one call fails the whole turn). Set to
# "true" to use the slower, more resilient multi-pass map-then-reduce pipeline
# instead — one call per file (skipping any that error, e.g. an HTTP 403 —
# Safe Infer blocking that file), then a final call combines whatever succeeded.
MULTI_PASS_ENABLED = os.getenv("ENABLE_MULTI_PASS", "false").strip().lower() == "true"

# Set DEBUG=true to append a "⏱ Timing" breakdown to every response. Off by
# default — this is a diagnostic aid, not something end users need to see.
DEBUG_ENABLED = os.getenv("DEBUG", "false").strip().lower() == "true"

_raw_access = os.getenv("DOC_ACCESS_ALLOWED", "").strip()
try:
    _DOC_ACCESS_ALLOWED: dict = ast.literal_eval(_raw_access) if _raw_access else {}
    if not isinstance(_DOC_ACCESS_ALLOWED, dict):
        _DOC_ACCESS_ALLOWED = {}
except Exception:
    _DOC_ACCESS_ALLOWED = {}

# Optional filename -> topic description hints, e.g.
# {'Board Meeting Summary Doc.docx': 'questions about the board meeting'}.
# Injected into the system prompt so the LLM routes a question to the
# relevant file(s) among whatever content is actually included that turn,
# rather than blending unrelated files together.
_raw_file_topics = os.getenv("FILE_TOPIC_HINTS", "").strip()
try:
    _FILE_TOPIC_HINTS: dict = ast.literal_eval(_raw_file_topics) if _raw_file_topics else {}
    if not isinstance(_FILE_TOPIC_HINTS, dict):
        _FILE_TOPIC_HINTS = {}
except Exception:
    _FILE_TOPIC_HINTS = {}


def _file_topic_hint_clause() -> str:
    """Build a system-prompt clause routing questions to the relevant file(s),
    or "" if FILE_TOPIC_HINTS isn't configured."""
    if not _FILE_TOPIC_HINTS:
        return ""
    mapping = "; ".join(f"'{fname}' is for {topic}" for fname, topic in _FILE_TOPIC_HINTS.items())
    return (
        f" Some files map to specific topics: {mapping}. When the user's question "
        "clearly relates to one of these topics, use ONLY the matching file's "
        "content (ignore the other files' content); if the question doesn't "
        "match any listed topic, or several files are relevant, use whichever "
        "file(s) actually apply based on their content."
    )


def _is_file_readable(file_path: str, pebblo_user_groups: str) -> bool:
    """Return True if the user may see/use file_path.

    Checks against DOC_ACCESS_ALLOWED (filename -> list of allowed groups).
    Files not present as keys are open to all users. Applies to both the
    Documents sidebar listing and the map-reduce pipeline's eligible files.
    """
    if not _DOC_ACCESS_ALLOWED:
        return True
    fname = os.path.basename(file_path.strip())
    if fname not in _DOC_ACCESS_ALLOWED:
        return True
    allowed = set(_DOC_ACCESS_ALLOWED[fname])
    user_groups = {g.strip() for g in (pebblo_user_groups or "").split(",") if g.strip()}
    return bool(user_groups & allowed)


def _list_docs(directory: str) -> list:
    """Return [(filename, full_path), ...] for all non-hidden files in directory."""
    if not os.path.isdir(directory):
        return []
    return [
        (fname, os.path.join(directory, fname))
        for fname in sorted(os.listdir(directory))
        if not fname.startswith(".") and os.path.isfile(os.path.join(directory, fname))
    ]


def _render_file_link(fname: str, fpath: str) -> None:
    """Render a sidebar link that opens the file in a new browser tab, if the
    file is servable (i.e. lives under static/, per Streamlit's
    enableStaticServing). Falls back to a plain (non-clickable) caption for
    any file outside static/ — e.g. a custom absolute DOCS_DIR/DECK_SOURCE_DIR.
    """
    rel = os.path.relpath(fpath, _STATIC_ROOT)
    if rel.startswith("..") or os.path.isabs(rel):
        st.caption(f"📄 {fname}")
        return
    url = f"/app/static/{rel.replace(os.sep, '/')}"
    st.markdown(
        f'<a href="{url}" target="_blank" style="font-size:0.85rem;text-decoration:none;">📄 {fname}</a>',
        unsafe_allow_html=True,
    )


def _render_docs_section(pebblo_groups: str = None, include_reference_docs: bool = True) -> None:
    """Sidebar 'Documents' block: DOCS_DIR (Safe Infer only) plus, if present,
    DECK_SOURCE_DIR — both rendered as clickable links (both live under
    static/ by default).

    pebblo_groups=None means "no gating" (Insecure Inference has no Pebblo
    user/group concept); otherwise files are hidden (🔒) per DOC_ACCESS_ALLOWED,
    matching what the pipeline will actually process.
    """
    docs = _list_docs(DOCS_DIR) if include_reference_docs else []
    sources = _list_docs(DECK_SOURCE_DIR)
    if not docs and not sources:
        return

    st.subheader("📁 Documents")
    if docs:
        for fname, fpath in docs:
            if pebblo_groups is None or _is_file_readable(fname, pebblo_groups):
                _render_file_link(fname, fpath)
            else:
                st.caption(f"🔒 {fname}")
    if sources:
        st.caption("Deck source files (used for generation)")
        for fname, fpath in sources:
            if pebblo_groups is None or _is_file_readable(fname, pebblo_groups):
                _render_file_link(fname, fpath)
            else:
                st.caption(f"🔒 {fname}")
    st.markdown("---")


# ---------------------------------------------------------------------------
# Shared upload handling (used identically by both modes)
# ---------------------------------------------------------------------------

def _process_upload_and_message(user_input: str, uploaded_file) -> tuple:
    """Combine the typed instructions with any uploaded file.

    Returns (augmented_content, display_content):
      - augmented_content: what gets sent to the LLM (may include parsed file text).
      - display_content: what gets shown in the chat bubble (never the raw file dump).

    Aborts the send (st.stop()) if a supported upload fails to parse.
    """
    if uploaded_file is None:
        return user_input, user_input

    name = uploaded_file.name
    if is_supported_file(name):
        try:
            file_text = parse_file_to_text(uploaded_file.getvalue(), filename=name)
        except FileParsingError as exc:
            st.error(str(exc))
            st.stop()
        augmented = f"File content from '{name}':\n\n{file_text}\n\nInstructions:\n{user_input}"
        display = f"{user_input}\n\n📎 Attached: {name}"
        return augmented, display

    st.warning(f"'{name}' is not a supported file type — sending your instructions without file content.")
    display = f"{user_input}\n\n📎 Attached (not parsed): {name}"
    return user_input, display


def _eligible_source_files(pebblo_groups: str = None) -> tuple:
    """Return (eligible, locked) from DECK_SOURCE_DIR.

    eligible: [(fname, fpath), ...] — supported files (.xlsx/.xlsm/.docx) the
      current user may use (all of them when pebblo_groups is None, i.e.
      Insecure Inference).
    locked: [fname, ...] — files that exist but are excluded by DOC_ACCESS_ALLOWED.
    Unsupported files in the folder are silently ignored.
    """
    eligible, locked = [], []
    for fname, fpath in _list_docs(DECK_SOURCE_DIR):
        if not is_supported_file(fname):
            continue
        if pebblo_groups is not None and not _is_file_readable(fname, pebblo_groups):
            locked.append(fname)
            continue
        eligible.append((fname, fpath))
    return eligible, locked


def _fmt_secs(seconds: float) -> str:
    return f"{seconds:.2f}s"


# ---------------------------------------------------------------------------
# LLM calls — Safe Infer (via Daxa gateway) and Insecure Inference (direct)
#
# Folder-iteration pipeline: when no file is uploaded directly, every eligible
# file in DECK_SOURCE_DIR is used. By default (MULTI_PASS_ENABLED=false) all
# of them are combined into ONE prompt and sent as a single call — fastest,
# but a block/error on that one call fails the whole turn. Set
# ENABLE_MULTI_PASS=true for the slower, more resilient alternative: one
# non-streaming "map" call per file, skipping any that error (in particular an
# HTTP 403 — Safe Infer blocking that content), then a final streaming
# "reduce" call combines whatever succeeded — a blocked file never prevents
# the rest of the deck from being generated.
# ---------------------------------------------------------------------------

_FILENAME_HINT = (
    "Filenames are meaningful: a file whose name contains 'employee' holds employee "
    "details, and a file whose name contains 'client' holds client details — use "
    "this to correctly label and organize the corresponding content."
)
_FILE_TOPIC_HINT = _file_topic_hint_clause()

DECK_SYSTEM_PROMPT = (
    "You are a slide deck generation assistant. Given file content (spreadsheet "
    "and/or document) and a user's instructions, produce a slide-by-slide outline "
    "in Markdown. For each slide, include a heading and 2-5 concise bullet points, "
    "grounded strictly in the provided file content and the user's stated goal. If "
    "no file content was provided, produce a reasonable outline from the "
    "instructions alone and say so briefly at the top. If any values in the file "
    "content appear masked or redacted (e.g. shown as asterisks, '[REDACTED]', "
    "'XXXX', or similar placeholders in place of what looks like sensitive "
    "information or PII), do not attempt to guess or reconstruct the original "
    "values — build the outline using the masked values as given, and add a brief "
    "note at the end of the outline flagging which field(s) appeared masked. "
    f"{_FILENAME_HINT}{_FILE_TOPIC_HINT}"
)

MAP_SYSTEM_PROMPT = (
    "You are a slide deck generation assistant. You are given the content of ONE "
    "file (a spreadsheet or a document), plus the user's overall instructions for "
    "the deck they want. Produce a short list of key points relevant to those "
    "instructions, based only on this file's content — these notes will later be "
    "combined with notes from other files into one final deck, so keep them "
    "concise (a handful of bullet points, no heading needed). If any values appear "
    "masked or redacted (e.g. asterisks, '[REDACTED]', 'XXXX'), do not guess the "
    "original value — use it as given and note which field(s) appeared masked. "
    f"{_FILENAME_HINT}{_FILE_TOPIC_HINT}"
)

REDUCE_SYSTEM_PROMPT = (
    "You are a slide deck generation assistant. You are given short notes gathered "
    "from one or more source files, plus the user's overall instructions. Combine "
    "them into ONE cohesive slide-by-slide outline in Markdown. For each slide, "
    "include a heading and 2-5 concise bullet points, grounded in the provided "
    "notes and the user's stated goal. If any note mentions a masked or redacted "
    "field, preserve that mention rather than guessing the real value. If no notes "
    "were provided, produce a reasonable outline from the instructions alone and "
    f"say so briefly at the top. {_FILENAME_HINT}{_FILE_TOPIC_HINT}"
)


def _call_once(client: OpenAI, model: str, system_prompt: str, content: str, timing: dict = None) -> str:
    """Single non-streaming completion. Raises on API/network errors (caller decides).

    If given, populates timing["call_s"] with the call's wall-clock duration.
    """
    start = time.perf_counter()
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": content}],
        stream=False,
    )
    if timing is not None:
        timing["call_s"] = time.perf_counter() - start
    return resp.choices[0].message.content or ""


def _call_stream(client: OpenAI, model: str, system_prompt: str, content: str, timing: dict = None):
    """Streaming completion. If given, populates timing["first_token_s"] (time to
    first content chunk) and timing["total_s"] (full call duration) once exhausted.
    """
    start = time.perf_counter()
    first_token_at = None
    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": content}],
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            if first_token_at is None:
                first_token_at = time.perf_counter()
            yield delta
    if timing is not None:
        timing["first_token_s"] = (first_token_at - start) if first_token_at is not None else None
        timing["total_s"] = time.perf_counter() - start


def _map_source_files(client: OpenAI, model: str, eligible: list, user_input: str) -> tuple:
    """Map phase: one non-streaming call per eligible file, shown live via st.status.

    Returns (partials, skipped, file_timings):
      partials: [(fname, partial_text), ...] for files that succeeded.
      skipped:  [(fname, reason), ...] for files that errored (403 = blocked by
        Safe Infer; anything else is a generic error) — never aborts the run.
      file_timings: [(fname, parse_s, call_s), ...] for every attempted file
        (call_s is 0.0 for files that errored before/without completing a call).
    """
    partials, skipped, file_timings = [], [], []
    with st.status(f"Processing {len(eligible)} source file(s)...", expanded=True) as status_box:
        for fname, fpath in eligible:
            parse_start = time.perf_counter()
            try:
                with open(fpath, "rb") as f:
                    file_text = parse_file_to_text(f.read(), filename=fname)
                parse_s = time.perf_counter() - parse_start
                map_content = (
                    f"File content from '{fname}':\n\n{file_text}\n\n"
                    f"Overall instructions:\n{user_input}"
                )
                call_timing: dict = {}
                partial = _call_once(client, model, MAP_SYSTEM_PROMPT, map_content, timing=call_timing)
                partials.append((fname, partial))
                call_s = call_timing.get("call_s", 0.0)
                file_timings.append((fname, parse_s, call_s))
                status_box.write(f"✅ {fname} — parse {_fmt_secs(parse_s)}, call {_fmt_secs(call_s)}")
            except APIStatusError as exc:
                parse_s = time.perf_counter() - parse_start
                status_code = getattr(exc, "status_code", None)
                reason = "blocked (HTTP 403)" if status_code == 403 else f"error (HTTP {status_code})"
                skipped.append((fname, reason))
                file_timings.append((fname, parse_s, 0.0))
                status_box.write(f"❌ {fname} — {reason}")
            except (FileParsingError, OSError):
                parse_s = time.perf_counter() - parse_start
                skipped.append((fname, "could not read/parse file"))
                file_timings.append((fname, parse_s, 0.0))
                status_box.write(f"❌ {fname} — could not read/parse file")
            except Exception as exc:
                parse_s = time.perf_counter() - parse_start
                skipped.append((fname, f"error: {exc}"))
                file_timings.append((fname, parse_s, 0.0))
                status_box.write(f"❌ {fname} — error")
        status_box.update(
            label=f"Processed {len(eligible)} file(s): {len(partials)} succeeded, {len(skipped)} skipped.",
            state="complete",
        )
    return partials, skipped, file_timings


def _reduce_stream(client: OpenAI, model: str, partials: list, user_input: str, skipped: list, locked: list, timing: dict = None):
    """Final streaming call combining collected partials, plus a deterministic
    (not LLM-generated) skip-summary note appended after streaming completes."""
    if partials:
        combined = "\n\n".join(f"--- Notes from {fname} ---\n{text}" for fname, text in partials)
        content = f"{combined}\n\nOverall instructions:\n{user_input}"
    else:
        content = user_input
    yield from _call_stream(client, model, REDUCE_SYSTEM_PROMPT, content, timing=timing)

    note_parts = []
    if skipped:
        detail = ", ".join(f"{fname} ({reason})" for fname, reason in skipped)
        note_parts.append(f"{len(skipped)} source file(s) could not be processed and were excluded: {detail}")
    if locked:
        note_parts.append(f"{len(locked)} file(s) were not accessible to the current user: {', '.join(locked)}")
    if note_parts:
        yield f"\n\n---\n*Note: {'; '.join(note_parts)}.*"


def _timing_note(label: str, timing: dict, total_s: float) -> str:
    first = timing.get("first_token_s")
    call_s = timing.get("total_s", timing.get("call_s", total_s))
    first_part = f" (first token {_fmt_secs(first)})" if first is not None else ""
    return f"⏱ Timing: {label} {_fmt_secs(call_s)}{first_part}; total {_fmt_secs(total_s)}."


def _build_combined_source_content(eligible: list, user_input: str) -> tuple:
    """Read+parse every eligible file and concatenate into ONE prompt (single pass).

    Returns (content, parse_total_s, parse_skipped):
      content: combined "File: <name>\\n<text>" sections + the user's instructions
        (falls back to just the instructions if every file failed to parse).
      parse_total_s: total time spent reading/parsing (not calling the LLM).
      parse_skipped: [(fname, reason), ...] for files that failed to parse —
        this is a local, pre-call check, so skipping them costs no LLM call
        (unlike an LLM-side block, which single pass cannot skip around).
    """
    sections, parse_skipped = [], []
    parse_total = 0.0
    for fname, fpath in eligible:
        start = time.perf_counter()
        try:
            with open(fpath, "rb") as f:
                file_text = parse_file_to_text(f.read(), filename=fname)
            sections.append(f"File: {fname}\n\n{file_text}")
        except (FileParsingError, OSError):
            parse_skipped.append((fname, "could not read/parse file"))
        parse_total += time.perf_counter() - start
    combined = "\n\n".join(sections)
    content = f"{combined}\n\nOverall instructions:\n{user_input}" if combined else user_input
    return content, parse_total, parse_skipped


def run_deck_pipeline(client: OpenAI, model: str, user_input: str, augmented_upload_content: str = None, pebblo_groups: str = None):
    """Shared entry point for both Safe Infer and Insecure Inference.

    augmented_upload_content is not None -> a file was uploaded directly:
      single streaming call using only that file (no folder iteration).
    augmented_upload_content is None -> no file uploaded: use eligible
      DECK_SOURCE_DIR files (gated by pebblo_groups if given) — combined into
      one call by default (MULTI_PASS_ENABLED=false), or via the slower,
      per-file map-then-reduce pipeline if MULTI_PASS_ENABLED=true.

    Skip/lock notes (which files were excluded and why) are always shown when
    relevant. The "⏱ Timing" breakdown is a diagnostic aid, only appended when
    DEBUG_ENABLED (env DEBUG=true) — off by default.
    """
    pipeline_start = time.perf_counter()

    if augmented_upload_content is not None:
        timing: dict = {}
        yield from _call_stream(client, model, DECK_SYSTEM_PROMPT, augmented_upload_content, timing=timing)
        if DEBUG_ENABLED:
            total_s = time.perf_counter() - pipeline_start
            yield f"\n\n---\n*{_timing_note('LLM call', timing, total_s)}*"
        return

    eligible, locked = _eligible_source_files(pebblo_groups)
    if not eligible:
        timing: dict = {}
        yield from _call_stream(client, model, DECK_SYSTEM_PROMPT, user_input, timing=timing)
        trailer = []
        if locked:
            trailer.append(f"*Note: {len(locked)} file(s) were not accessible to the current user: {', '.join(locked)}.*")
        if DEBUG_ENABLED:
            total_s = time.perf_counter() - pipeline_start
            trailer.append(f"*{_timing_note('LLM call', timing, total_s)}*")
        if trailer:
            yield "\n\n---\n" + "\n\n".join(trailer)
        return

    if MULTI_PASS_ENABLED:
        partials, skipped, file_timings = _map_source_files(client, model, eligible, user_input)
        reduce_timing: dict = {}
        yield from _reduce_stream(client, model, partials, user_input, skipped, locked, timing=reduce_timing)

        if DEBUG_ENABLED:
            total_s = time.perf_counter() - pipeline_start
            parse_total = sum(p for _, p, _ in file_timings)
            map_call_total = sum(c for _, _, c in file_timings)
            per_file = ", ".join(f"{fn} {_fmt_secs(c)}" for fn, _, c in file_timings)
            reduce_first = reduce_timing.get("first_token_s")
            reduce_total = reduce_timing.get("total_s", 0.0)
            reduce_first_part = f" (first token {_fmt_secs(reduce_first)})" if reduce_first is not None else ""
            yield (
                f"\n\n*⏱ Timing: parse {_fmt_secs(parse_total)}; "
                f"map calls {_fmt_secs(map_call_total)} ({per_file}); "
                f"reduce call {_fmt_secs(reduce_total)}{reduce_first_part}; "
                f"total {_fmt_secs(total_s)}.*"
            )
        return

    # Single pass (default): one call with every eligible file's content combined.
    content, parse_s, parse_skipped = _build_combined_source_content(eligible, user_input)
    timing = {}
    yield from _call_stream(client, model, DECK_SYSTEM_PROMPT, content, timing=timing)

    note_parts = []
    if parse_skipped:
        detail = ", ".join(f"{fname} ({reason})" for fname, reason in parse_skipped)
        note_parts.append(f"{len(parse_skipped)} source file(s) could not be parsed and were excluded: {detail}")
    if locked:
        note_parts.append(f"{len(locked)} file(s) were not accessible to the current user: {', '.join(locked)}")

    trailer = []
    if note_parts:
        trailer.append(f"*Note: {'; '.join(note_parts)}.*")
    if DEBUG_ENABLED:
        total_s = time.perf_counter() - pipeline_start
        first = timing.get("first_token_s")
        first_part = f" (first token {_fmt_secs(first)})" if first is not None else ""
        trailer.append(
            f"*⏱ Timing: parse {_fmt_secs(parse_s)}; "
            f"LLM call {_fmt_secs(timing.get('total_s', total_s))}{first_part}; "
            f"total {_fmt_secs(total_s)}.*"
        )
    if trailer:
        yield "\n\n---\n" + "\n\n".join(trailer)


def stream_deck_builder(
    user_input: str,
    model: str,
    augmented_upload_content: str = None,
    api_key: str = "",
    pebblo_user: str = "",
    pebblo_user_groups: str = "",
):
    """Safe Infer: routed through the Daxa gateway with Pebblo headers."""
    client = get_llm_client(api_key or API_KEY, pebblo_user=pebblo_user, pebblo_user_groups=pebblo_user_groups)
    yield from run_deck_pipeline(client, model, user_input, augmented_upload_content, pebblo_groups=pebblo_user_groups or None)


def stream_deck_builder_direct(user_input: str, model: str, augmented_upload_content: str = None):
    """Insecure Inference: direct to the configured model, no Daxa gateway, no Pebblo headers.

    Uses the exact same run_deck_pipeline as Safe Infer — only the client differs.
    """
    client = get_direct_llm_client()
    yield from run_deck_pipeline(client, model, user_input, augmented_upload_content, pebblo_groups=None)


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def fetch_models():
    """Fetch models from GET .../v1/models (cached 5 min). Returns (names, default_id)."""
    return get_available_models()


st.set_page_config(
    page_title="Deck Builder App",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

LANGUAGE_PROMPTS = load_prompts_from_yaml()
DEFAULT_LANGUAGE = "en" if "en" in LANGUAGE_PROMPTS else (list(LANGUAGE_PROMPTS.keys())[0] if LANGUAGE_PROMPTS else "en")

# Feature flags — control which mode tabs are visible. Unset or blank means
# "shown"; only an explicit "false" hides a mode (blank is common when a var
# is present in .env.example but not filled in).
SHOW_SAFE_INFER = os.getenv("SHOW_SAFE_INFER", "true").strip().lower() != "false"
SHOW_INSECURE_INFER = os.getenv("SHOW_INSECURE_INFER", "true").strip().lower() != "false"

_MODE_LABELS = {"Safe Infer": "🟢 Safe Infer", "Insecure Inference": "🔴 Insecure Inference"}
_LABEL_TO_MODE = {v: k for k, v in _MODE_LABELS.items()}
_MODE_OPTIONS = [
    *(["🟢 Safe Infer"] if SHOW_SAFE_INFER else []),
    *(["🔴 Insecure Inference"] if SHOW_INSECURE_INFER else []),
]
_DEFAULT_MODE = _MODE_OPTIONS[0] if _MODE_OPTIONS else "🟢 Safe Infer"

# Session state
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "direct_chat_history" not in st.session_state:
    st.session_state.direct_chat_history = []
if "selected_model" not in st.session_state:
    st.session_state.selected_model = MODEL or ""
if "api_key" not in st.session_state:
    st.session_state.api_key = API_KEY
if "model_name" not in st.session_state:
    st.session_state.model_name = ""
if "prompt_language" not in st.session_state:
    st.session_state.prompt_language = DEFAULT_LANGUAGE
if "selected_pebblo_user" not in st.session_state:
    st.session_state.selected_pebblo_user = PEBBLO_USERS_LIST[0] if PEBBLO_USERS_LIST else (X_PEBBLO_USER or "")


def _get_active_pebblo_groups() -> str:
    """Return user-groups string for the selected user, falling back to env default."""
    user = st.session_state.get("selected_pebblo_user", "")
    if user and PEBBLO_USER_GROUPS_MAP:
        mapped = PEBBLO_USER_GROUPS_MAP.get(user, "")
        if mapped:
            return mapped
    return X_PEBBLO_USER_GROUPS or ""


def _render_prompt_language_and_samples() -> None:
    """Prompt-language selector + Sample Prompts — shared by both modes."""
    st.subheader("🌐 Prompt language")
    lang_options = list(LANGUAGE_PROMPTS.keys()) if LANGUAGE_PROMPTS else [DEFAULT_LANGUAGE]
    try:
        lang_index = lang_options.index(st.session_state.prompt_language)
    except ValueError:
        lang_index = 0
        st.session_state.prompt_language = lang_options[0] if lang_options else DEFAULT_LANGUAGE
    selected_lang = st.selectbox(
        "Language",
        options=lang_options,
        index=lang_index,
        key="prompt_language_select",
        label_visibility="collapsed",
    )
    st.session_state.prompt_language = selected_lang

    st.subheader("📝 Sample Prompts")
    prompts_for_lang = LANGUAGE_PROMPTS.get(selected_lang, [])
    for i, prompt in enumerate(prompts_for_lang):
        label = prompt.get("label", "")
        copyable_text = prompt.get("copyable", "")
        st.markdown('<span class="prompt-use-btn-marker"></span>', unsafe_allow_html=True)
        col_cap, col_btn = st.columns([3, 1])
        with col_cap:
            st.caption(f"**{label}**")
        with col_btn:
            if st.button("→", key=f"use_prompt_{selected_lang}_{i}", help="Copy to message box"):
                st.session_state.user_input = copyable_text
                st.session_state.direct_user_input = copyable_text
                st.rerun()
        st.text_area(
            "Prompt",
            value=copyable_text,
            height=min(120, 60 + copyable_text.count("\n") * 24),
            disabled=True,
            key=f"sidebar_prompt_{selected_lang}_{i}",
            label_visibility="collapsed",
        )


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.caption(f"🔗 Target: {API_BASE_URL}")
    st.markdown("---")

    _raw_mode = st.segmented_control(
        "Mode",
        options=_MODE_OPTIONS,
        default=_DEFAULT_MODE,
        key="app_mode",
        label_visibility="collapsed",
    )
    mode = _LABEL_TO_MODE.get(_raw_mode, "Safe Infer")
    st.markdown("---")

    if mode == "Safe Infer":
        if PEBBLO_USERS_LIST:
            st.subheader("👤 User")
            st.selectbox(
                "User",
                options=PEBBLO_USERS_LIST,
                format_func=format_display_name,
                key="selected_pebblo_user",
                label_visibility="collapsed",
            )
            st.markdown("---")

        st.subheader("🔗 API Status")
        if st.button("Test API Connection"):
            with st.spinner("Testing connection..."):
                result = test_api_connection()
                if result["status"] == "success":
                    st.success(result["message"])
                else:
                    st.error(result["message"])

        st.subheader("🤖 Model")
        model_names, default_model = fetch_models()
        model_names = merge_env_model_into_model_list(model_names, MODEL)
        if model_names:
            try:
                current = st.session_state.get("selected_model") or MODEL or default_model
                if current not in model_names:
                    current = default_model or model_names[0]
                idx = model_names.index(current) if current in model_names else 0
            except (ValueError, TypeError):
                idx = 0
            selected_model = st.selectbox(
                "LLM Model",
                model_names,
                index=idx,
                key="sidebar_model_select",
                label_visibility="collapsed",
            )
            st.session_state.selected_model = selected_model
            st.session_state.model_name = selected_model
        else:
            st.warning("Could not load models from API. Enter a model ID below.")
            fallback = st.session_state.get("selected_model") or MODEL or ""
            manual = st.text_input(
                "Model ID",
                value=fallback,
                key="sidebar_model_manual",
                placeholder="Enter model id",
            )
            if manual.strip():
                st.session_state.selected_model = manual.strip()
                st.session_state.model_name = manual.strip()
        if st.button("Refresh models", key="refresh_models_main"):
            fetch_models.clear()
            st.rerun()

        _render_prompt_language_and_samples()

        _render_docs_section(pebblo_groups=_get_active_pebblo_groups())

        st.subheader("📊 Statistics")
        st.metric("Messages", len(st.session_state.chat_history))
        st.markdown(
            f"""
<div style="font-size:0.8rem;">
    Current Model: <br><span style="font-size:1.2rem;"><b>{st.session_state.model_name}</b></span>
</div>
""",
            unsafe_allow_html=True,
        )

    elif mode == "Insecure Inference":
        st.subheader("🤖 Model")
        _direct_model_val = st.session_state.get("direct_model") or MODEL or "gpt-5"
        st.text_input(
            "Model ID",
            value=_direct_model_val,
            key="direct_model",
            placeholder="e.g. gpt-5, gpt-4o-mini",
        )
        st.caption("Calls the model directly using `OPENAI_API_KEY` — no Daxa gateway, no Pebblo headers.")

        _render_prompt_language_and_samples()

        _render_docs_section(pebblo_groups=None, include_reference_docs=False)

        st.subheader("📊 Statistics")
        st.metric("Messages", len(st.session_state.direct_chat_history))
        st.markdown(
            f"""
<div style="font-size:0.8rem;">
    Current Model: <br><span style="font-size:1.2rem;"><b>{st.session_state.direct_model}</b></span>
</div>
""",
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------

st.markdown(MAIN_HEADER_HTML, unsafe_allow_html=True)

if mode == "Safe Infer":
    _welcome_user = st.session_state.get("selected_pebblo_user", "") or None
    _welcome_group = (_get_active_pebblo_groups().split(",")[0].strip()) or None
    st.markdown(get_welcome_html(user_email=_welcome_user, user_team=_welcome_group), unsafe_allow_html=True)

    for message in st.session_state.chat_history:
        display_chat_message(
            role=message["role"],
            content=message["content"],
            model=message.get("model", ""),
            user=message.get("user", ""),
            timestamp=message.get("timestamp", ""),
        )

    with st.expander("📎 Upload a file (optional)", expanded=False):
        uploaded_file = st.file_uploader(
            "File",
            type=None,
            key="uploaded_file",
            help="If provided, only this file is used (the source-files folder is not "
            "iterated). Supports .xlsx, .xlsm, .docx — other file types are sent as "
            "instructions-only.",
            label_visibility="collapsed",
        )
    user_input = st.text_area(
        "Type your instructions here:",
        height=100,
        placeholder="e.g. Build a 5-slide investor update from this data.",
        key="user_input",
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        send_button = st.button("🚀 Generate Outline", type="primary")

    if send_button and user_input.strip():
        active_user = st.session_state.get("selected_pebblo_user", "")
        augmented_content, display_content = _process_upload_and_message(user_input, uploaded_file)
        upload_content_for_pipeline = augmented_content if uploaded_file is not None else None

        st.session_state.chat_history.append({
            "role": "user",
            "content": display_content,
            "user": active_user,
            "timestamp": time.strftime("%H:%M:%S"),
        })
        display_chat_message("user", display_content, user=active_user)

        model = (st.session_state.get("selected_model") or "").strip()
        if not model:
            st.error("No model selected. Load models from API or enter a model ID.")
            st.stop()

        try:
            with st.chat_message("assistant"):
                response = st.write_stream(
                    stream_deck_builder(
                        user_input=user_input,
                        model=model,
                        augmented_upload_content=upload_content_for_pipeline,
                        api_key=st.session_state.api_key,
                        pebblo_user=active_user,
                        pebblo_user_groups=_get_active_pebblo_groups(),
                    )
                )
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": response,
                "model": st.session_state.selected_model,
                "user": active_user,
                "timestamp": time.strftime("%H:%M:%S"),
            })
        except Exception as e:
            error_message = f"❌ Error: {str(e)}"
            st.error(error_message)
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": error_message,
                "timestamp": time.strftime("%H:%M:%S"),
            })

        st.rerun()

elif mode == "Insecure Inference":
    for message in st.session_state.direct_chat_history:
        display_chat_message(
            role=message["role"],
            content=message["content"],
            model=message.get("model", ""),
            timestamp=message.get("timestamp", ""),
        )

    with st.expander("📎 Upload a file (optional)", expanded=False):
        direct_uploaded_file = st.file_uploader(
            "File",
            type=None,
            key="direct_uploaded_file",
            help="If provided, only this file is used (the source-files folder is not "
            "iterated). Supports .xlsx, .xlsm, .docx — other file types are sent as "
            "instructions-only.",
            label_visibility="collapsed",
        )
    direct_user_input = st.text_area(
        "Type your instructions here:",
        height=100,
        placeholder="e.g. Build a 5-slide investor update from this data.",
        key="direct_user_input",
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        direct_send = st.button("🚀 Generate Outline", type="primary", key="direct_send_btn")

    if direct_send and direct_user_input.strip():
        augmented_content, display_content = _process_upload_and_message(direct_user_input, direct_uploaded_file)
        direct_upload_content_for_pipeline = augmented_content if direct_uploaded_file is not None else None

        st.session_state.direct_chat_history.append({
            "role": "user",
            "content": display_content,
            "timestamp": time.strftime("%H:%M:%S"),
        })
        display_chat_message("user", display_content)

        direct_model = (st.session_state.get("direct_model") or MODEL or "gpt-5").strip()

        try:
            with st.chat_message("assistant"):
                response = st.write_stream(
                    stream_deck_builder_direct(
                        user_input=direct_user_input,
                        model=direct_model,
                        augmented_upload_content=direct_upload_content_for_pipeline,
                    )
                )
            st.session_state.direct_chat_history.append({
                "role": "assistant",
                "content": response,
                "model": direct_model,
                "timestamp": time.strftime("%H:%M:%S"),
            })
        except Exception as e:
            error_message = f"❌ Error: {str(e)}"
            st.error(error_message)
            st.session_state.direct_chat_history.append({
                "role": "assistant",
                "content": error_message,
                "timestamp": time.strftime("%H:%M:%S"),
            })

        st.rerun()

# Footer
st.markdown("---")
st.markdown(FOOTER_HTML, unsafe_allow_html=True)
