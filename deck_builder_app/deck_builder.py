"""Deck Builder App — upload a spreadsheet + instructions, get a slide outline back.

Two modes, selectable from the sidebar:
  - Safe Infer:         routed through the Daxa/Proxima SafeInfer gateway (Pebblo headers).
  - Insecure Inference:  calls the configured model directly, no gateway, no Pebblo headers.
"""
import ast
import os
import time

import streamlit as st

from file_parser import FileParsingError, parse_xlsx_to_text
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
# Documents section config (Safe Infer sidebar only — plain reference links,
# not exposed to the LLM as tools)
# ---------------------------------------------------------------------------

_APP_DIR = os.path.dirname(__file__)
_raw_docs_dir = os.getenv("DOCS_DIR", "").strip() or "static"
DOCS_DIR = _raw_docs_dir if os.path.isabs(_raw_docs_dir) else os.path.join(_APP_DIR, _raw_docs_dir)

_raw_access = os.getenv("DOC_ACCESS_ALLOWED", "").strip()
try:
    _DOC_ACCESS_ALLOWED: dict = ast.literal_eval(_raw_access) if _raw_access else {}
    if not isinstance(_DOC_ACCESS_ALLOWED, dict):
        _DOC_ACCESS_ALLOWED = {}
except Exception:
    _DOC_ACCESS_ALLOWED = {}


def _is_file_readable(file_path: str, pebblo_user_groups: str) -> bool:
    """Return True if the user may see file_path in the Documents list.

    Checks against DOC_ACCESS_ALLOWED (filename -> list of allowed groups).
    Files not present as keys are open to all users.
    """
    if not _DOC_ACCESS_ALLOWED:
        return True
    fname = os.path.basename(file_path.strip())
    if fname not in _DOC_ACCESS_ALLOWED:
        return True
    allowed = set(_DOC_ACCESS_ALLOWED[fname])
    user_groups = {g.strip() for g in (pebblo_user_groups or "").split(",") if g.strip()}
    return bool(user_groups & allowed)


def _list_docs() -> list:
    """Return [(filename, full_path), ...] for all non-hidden files in DOCS_DIR."""
    if not os.path.isdir(DOCS_DIR):
        return []
    return [
        (fname, os.path.join(DOCS_DIR, fname))
        for fname in sorted(os.listdir(DOCS_DIR))
        if not fname.startswith(".") and os.path.isfile(os.path.join(DOCS_DIR, fname))
    ]


def _render_file_link(fname: str, fpath: str) -> None:
    """Render a sidebar link that opens the file in a new browser tab.

    Relies on Streamlit's static file serving (enableStaticServing = true).
    """
    rel = os.path.relpath(fpath, DOCS_DIR).replace(os.sep, "/")
    url = f"/app/static/{rel}"
    st.markdown(
        f'<a href="{url}" target="_blank" style="font-size:0.85rem;text-decoration:none;">📄 {fname}</a>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# LLM calls — Safe Infer (via Daxa gateway) and Insecure Inference (direct)
# ---------------------------------------------------------------------------

DECK_SYSTEM_PROMPT = (
    "You are a slide deck generation assistant. Given spreadsheet content and a "
    "user's instructions, produce a slide-by-slide outline in Markdown. For each "
    "slide, include a heading and 2-5 concise bullet points, grounded strictly in "
    "the provided spreadsheet data and the user's stated goal. If no spreadsheet "
    "content was provided, produce a reasonable outline from the instructions alone "
    "and say so briefly at the top. If any values in the spreadsheet content appear "
    "masked or redacted (e.g. shown as asterisks, '[REDACTED]', 'XXXX', or similar "
    "placeholders in place of what looks like sensitive information or PII), do not "
    "attempt to guess or reconstruct the original values — build the outline using "
    "the masked values as given, and add a brief note at the end of the outline "
    "flagging which field(s) appeared masked."
)


def _deck_messages(message: str) -> list:
    return [
        {"role": "system", "content": DECK_SYSTEM_PROMPT},
        {"role": "user", "content": message},
    ]


def stream_deck_builder(message: str, model: str, api_key: str = "", pebblo_user: str = "", pebblo_user_groups: str = ""):
    """Safe Infer: routed through the Daxa gateway with Pebblo headers."""
    client = get_llm_client(api_key or API_KEY, pebblo_user=pebblo_user, pebblo_user_groups=pebblo_user_groups)
    stream = client.chat.completions.create(model=model, messages=_deck_messages(message), stream=True)
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


def stream_deck_builder_direct(message: str, model: str):
    """Insecure Inference: direct to the configured model, no Daxa gateway, no Pebblo headers."""
    client = get_direct_llm_client()
    stream = client.chat.completions.create(model=model, messages=_deck_messages(message), stream=True)
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


# ---------------------------------------------------------------------------
# Shared upload handling (used identically by both modes)
# ---------------------------------------------------------------------------

def _extension_is_xlsx(filename: str) -> bool:
    return filename.lower().endswith((".xlsx", ".xlsm"))


def _process_upload_and_message(user_input: str, uploaded_file) -> tuple:
    """Combine the typed instructions with any uploaded spreadsheet.

    Returns (augmented_content, display_content):
      - augmented_content: what gets sent to the LLM (may include parsed sheet text).
      - display_content: what gets shown in the chat bubble (never the raw sheet dump).

    Aborts the send (st.stop()) if an .xlsx upload fails to parse.
    """
    if uploaded_file is None:
        return user_input, user_input

    name = uploaded_file.name
    if _extension_is_xlsx(name):
        try:
            sheet_text = parse_xlsx_to_text(uploaded_file.getvalue(), filename=name)
        except FileParsingError as exc:
            st.error(str(exc))
            st.stop()
        augmented = f"Spreadsheet content from '{name}':\n\n{sheet_text}\n\nInstructions:\n{user_input}"
        display = f"{user_input}\n\n📎 Attached: {name}"
        return augmented, display

    st.warning(f"'{name}' is not a .xlsx file — sending your instructions without file content.")
    display = f"{user_input}\n\n📎 Attached (not parsed): {name}"
    return user_input, display


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

        _docs = _list_docs()
        if _docs:
            st.subheader("📁 Documents")
            _current_groups = _get_active_pebblo_groups()
            for _fname, _fpath in _docs:
                if _is_file_readable(_fname, _current_groups):
                    _render_file_link(_fname, _fpath)
                else:
                    st.caption(f"🔒 {_fname}")
            st.markdown("---")

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

    col_up, col_txt = st.columns([1, 3])
    with col_up:
        uploaded_file = st.file_uploader(
            "Spreadsheet (optional)",
            type=None,
            key="uploaded_file",
            help="Primarily .xlsx — other file types are sent as instructions-only.",
        )
    with col_txt:
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
                        message=augmented_content,
                        model=model,
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

    col_up, col_txt = st.columns([1, 3])
    with col_up:
        direct_uploaded_file = st.file_uploader(
            "Spreadsheet (optional)",
            type=None,
            key="direct_uploaded_file",
            help="Primarily .xlsx — other file types are sent as instructions-only.",
        )
    with col_txt:
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
                        message=augmented_content,
                        model=direct_model,
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
